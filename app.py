# app.py — Bibliothèque GPX locale (lecture d'un dossier et affichage sur carte)
import os
import sys
import argparse
import tempfile
import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path

ST_AVAILABLE = False
try:
    import streamlit as st
    from streamlit_folium import st_folium
    import streamlit.components.v1 as components
    ST_AVAILABLE = True
except Exception:
    st = None
    st_folium = None
    components = None

try:
    import gpxpy
    import folium
    from folium.plugins import MarkerCluster
    import requests
except ModuleNotFoundError as e:
    print("[ERREUR] Modules requis manquants (gpxpy, folium).", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------------------------


@dataclass
class TrackData:
    """Données d'une trace GPX"""
    file_path: str
    folder_path: str
    name: str
    track: gpxpy.gpx.GPXTrack
    segment: gpxpy.gpx.GPXTrackSegment
    points: List[gpxpy.gpx.GPXTrackPoint]
    length: float
    elevation_gain: float
    start_time: Optional[str]
    end_time: Optional[str]
    keywords: List[str]  # Mots-clés extraits du chemin


@dataclass
class RouteData:
    """Données d'une route GPX"""
    file_path: str
    folder_path: str
    name: str
    route: gpxpy.gpx.GPXRoute
    points: List[gpxpy.gpx.GPXRoutePoint]
    length: float
    keywords: List[str]


@dataclass
class WaypointData:
    """Données d'un waypoint GPX"""
    file_path: str
    folder_path: str
    name: str
    waypoint: gpxpy.gpx.GPXWaypoint
    keywords: List[str]
    icon: Optional[str] = None  # Icône extraite du GPX

# ---------------------------------------------------------------------------------------------
# Classes principales
# ---------------------------------------------------------------------------------------------


class GPXProcessor:
    """Gestionnaire pour le traitement des fichiers GPX"""

    def __init__(self):
        self.tracks: List[TrackData] = []
        self.routes: List[RouteData] = []
        self.waypoints: List[WaypointData] = []

    def find_gpx_files(self, folders: List[str]) -> List[str]:
        """Trouve tous les fichiers GPX dans les dossiers spécifiés"""
        gpx_files = []
        for folder in folders:
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(".gpx"):
                        gpx_files.append(os.path.join(root, f))
        return gpx_files

    def extract_keywords(self, file_path: str) -> List[str]:
        """Extrait les mots-clés du chemin du fichier"""
        path_parts = Path(file_path).parts
        keywords = []
        for part in path_parts:
            if part and part not in ['/', '\\']:
                keywords.append(part.lower())
        return keywords

    def extract_waypoint_icon(self, waypoint: gpxpy.gpx.GPXWaypoint) -> Optional[str]:
        """Extrait l'icône d'un waypoint depuis les extensions GPX"""
        try:
            # Chercher dans les extensions pour osmand:icon
            if hasattr(waypoint, 'extensions') and waypoint.extensions:
                for ext in waypoint.extensions:
                    if hasattr(ext, 'tag') and 'osmand:icon' in ext.tag:
                        return ext.text.strip()

            # Chercher dans les extensions pour sym
            if hasattr(waypoint, 'extensions') and waypoint.extensions:
                for ext in waypoint.extensions:
                    if hasattr(ext, 'tag') and 'sym' in ext.tag:
                        return ext.text.strip()

            # Fallback: chercher dans les attributs du waypoint
            if hasattr(waypoint, 'symbol') and waypoint.symbol:
                return waypoint.symbol.strip()

        except Exception:
            pass
        return None

    def get_emoji_for_icon(self, icon: str, waypoint_name: str = "") -> str:
        """Convertit une icône GPX en emoji approprié, en utilisant aussi le nom du waypoint"""
        # Combiner l'icône et le nom pour une recherche plus intelligente
        search_text = f"{icon or ''} {waypoint_name or ''}".lower()
        search_text = search_text.replace(
            '_', ' ').replace('-', ' ').replace(',', ' ')

        # Mapping étendu des icônes vers des emojis (français + anglais)
        icon_mapping = {
            # Restaurants et nourriture
            'restaurant': '🍽️', 'restaurants': '🍽️', 'resto': '🍽️',
            'cafe': '☕', 'café': '☕', 'coffee': '☕', 'coffee shop': '☕',
            'bar': '🍺', 'pub': '🍺', 'brasserie': '🍺',
            'food': '🍕', 'nourriture': '🍕', 'manger': '🍕',
            'pizza': '🍕', 'pizzeria': '🍕',
            'burger': '🍔', 'hamburger': '🍔',
            'boulangerie': '🥖', 'bakery': '🥖', 'boulanger': '🥖',
            'patisserie': '🧁', 'pâtisserie': '🧁', 'patissier': '🧁',

            # Transport
            'car': '🚗', 'voiture': '🚗', 'auto': '🚗',
            'bus': '🚌', 'autobus': '🚌',
            'train': '🚂', 'gare': '🚂', 'station': '🚂',
            'metro': '🚇', 'métro': '🚇', 'subway': '🚇',
            'airport': '✈️', 'aéroport': '✈️', 'aeroport': '✈️',
            'parking': '🅿️', 'stationnement': '🅿️',
            'gas': '⛽', 'essence': '⛽', 'station service': '⛽',
            'bike': '🚴', 'vélo': '🚴', 'velo': '🚴', 'bicycle': '🚴',

            # Hébergement
            'hotel': '🏨', 'hôtel': '🏨', 'hotels': '🏨',
            'hostel': '🏨', 'auberge': '🏨',
            'camping': '⛺', 'camp': '⛺',
            'bed': '🛏️', 'lit': '🛏️', 'chambre': '🛏️',
            'gite': '🏠', 'gîte': '🏠', 'gites': '🏠',

            # Shopping
            'shop': '🛍️', 'magasin': '🛍️', 'boutique': '🛍️',
            'store': '🏪', 'commerce': '🏪',
            'market': '🏪', 'marché': '🏪', 'marche': '🏪',
            'pharmacy': '💊', 'pharmacie': '💊',
            'bank': '🏦', 'banque': '🏦',
            'atm': '🏧', 'distributeur': '🏧',
            'supermarket': '🏪', 'supermarché': '🏪', 'supermarche': '🏪',

            # Culture et loisirs
            'museum': '🏛️', 'musée': '🏛️', 'musee': '🏛️', 'museums': '🏛️',
            'theater': '🎭', 'théâtre': '🎭', 'theatre': '🎭',
            'cinema': '🎬', 'cinéma': '🎬', 'cinema': '🎬',
            'library': '📚', 'bibliothèque': '📚', 'bibliotheque': '📚',
            'book': '📖', 'livre': '📖', 'librairie': '📖',
            'music': '🎵', 'musique': '🎵',
            'art': '🎨', 'artiste': '🎨',
            'gallery': '🖼️', 'galerie': '🖼️',
            'theatre': '🎭', 'spectacle': '🎭',

            # Nature et extérieur
            'park': '🌳', 'parc': '🌳', 'jardin': '🌻',
            'garden': '🌻', 'jardins': '🌻',
            'beach': '🏖️', 'plage': '🏖️',
            'mountain': '⛰️', 'montagne': '⛰️', 'mont': '⛰️',
            'hiking': '🥾', 'randonnée': '🥾', 'randonnee': '🥾', 'trek': '🥾',
            'walking': '🚶', 'marche': '🚶', 'piéton': '🚶',
            'swimming': '🏊', 'natation': '🏊', 'piscine': '🏊',
            'summit': '⛰️', 'sommet': '⛰️', 'pic': '⛰️', 'peak': '⛰️',
            'viewpoint': '👁️', 'point de vue': '👁️', 'belvédère': '👁️',
            'binoculars': '🔭', 'jumelles': '🔭', 'observation': '🔭',
            'lac': '🏞️', 'lake': '🏞️', 'étang': '🏞️', 'etang': '🏞️',
            'rivière': '🏞️', 'riviere': '🏞️', 'river': '🏞️',

            # Spécial et étoiles
            'special': '⭐', 'spécial': '⭐', 'special': '⭐',
            'star': '⭐', 'étoile': '⭐', 'etoile': '⭐',
            'special star': '⭐', 'special_star': '⭐',
            'favorite': '❤️', 'favori': '❤️', 'favoris': '❤️',
            'important': '⭐', 'important': '⭐',
            'monument': '🏛️', 'monuments': '🏛️',
            'church': '⛪', 'église': '⛪', 'eglise': '⛪', 'chapelle': '⛪',
            'temple': '🛕', 'temple': '🛕',
            'mosque': '🕌', 'mosquée': '🕌', 'mosquee': '🕌',
            'château': '🏰', 'chateau': '🏰', 'castle': '🏰',
            'tour': '🗼', 'tower': '🗼',

            # Services
            'hospital': '🏥', 'hôpital': '🏥', 'hopital': '🏥',
            'police': '👮', 'gendarmerie': '👮', 'commissariat': '👮',
            'fire': '🚒', 'pompiers': '🚒', 'sapeurs': '🚒',
            'post': '📮', 'poste': '📮', 'la poste': '📮',
            'phone': '📞', 'téléphone': '📞', 'telephone': '📞',
            'wifi': '📶', 'internet': '📶',
            'mairie': '🏛️', 'town hall': '🏛️', 'hôtel de ville': '🏛️',

            # Divers
            'toilet': '🚻', 'wc': '🚻', 'toilettes': '🚻',
            'info': 'ℹ️', 'information': 'ℹ️', 'informations': 'ℹ️',
            'warning': '⚠️', 'attention': '⚠️', 'danger': '⚠️',
            'flag': '🚩', 'drapeau': '🚩',
            'home': '🏠', 'maison': '🏠', 'domicile': '🏠',
            'work': '💼', 'travail': '💼', 'bureau': '💼',
            'school': '🏫', 'école': '🏫', 'ecole': '🏫',
            'university': '🎓', 'université': '🎓', 'universite': '🎓',
            'cimetière': '⚰️', 'cimetiere': '⚰️', 'cemetery': '⚰️',
            'cave': '🍷', 'wine': '🍷', 'vin': '🍷',
            'fromage': '🧀', 'cheese': '🧀', 'fromagerie': '🧀'
        }

        # Recherche exacte d'abord
        for key, emoji in icon_mapping.items():
            if key in search_text:
                return emoji

        # Recherche par mots-clés dans le nom
        name_words = waypoint_name.lower().split()
        for word in name_words:
            # Nettoyer le mot (enlever ponctuation)
            clean_word = ''.join(c for c in word if c.isalnum())
            for key, emoji in icon_mapping.items():
                if clean_word == key or key in clean_word:
                    return emoji

        # Si rien ne correspond, retourner l'emoji par défaut
        return "📍"

    def calculate_elevation_gain(self, points: List[gpxpy.gpx.GPXTrackPoint]) -> float:
        """Calcule le dénivelé positif d'une trace"""
        if len(points) < 2:
            return 0.0

        elevation_gain = 0.0
        for i in range(1, len(points)):
            if points[i].elevation is not None and points[i-1].elevation is not None:
                diff = points[i].elevation - points[i-1].elevation
                if diff > 0:
                    elevation_gain += diff
        return elevation_gain

    def process_gpx_file(self, file_path: str, selected_folders: List[str]) -> None:
        """Traite un fichier GPX et extrait les données"""
        folder_path = os.path.dirname(file_path)
        if folder_path not in selected_folders:
            return

        keywords = self.extract_keywords(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)

            # Traitement des tracks
            for track in gpx.tracks:
                for segment in track.segments:
                    if segment.points:
                        elevation_gain = self.calculate_elevation_gain(
                            segment.points)
                        bounds = track.get_time_bounds()
                        start_time = bounds.start_time.isoformat() if bounds and bounds.start_time else None
                        end_time = bounds.end_time.isoformat() if bounds and bounds.end_time else None

                        track_data = TrackData(
                            file_path=file_path,
                            folder_path=folder_path,
                            name=os.path.basename(file_path),
                            track=track,
                            segment=segment,
                            points=segment.points,
                            length=track.length_3d(),
                            elevation_gain=elevation_gain,
                            start_time=start_time,
                            end_time=end_time,
                            keywords=keywords
                        )
                        self.tracks.append(track_data)

            # Traitement des routes
            for route in gpx.routes:
                if route.points:
                    length = sum(p.distance_3d(route.points[i-1]) if i > 0 else 0
                                 for i, p in enumerate(route.points))

                    route_data = RouteData(
                        file_path=file_path,
                        folder_path=folder_path,
                        name=os.path.basename(file_path),
                        route=route,
                        points=route.points,
                        length=length,
                        keywords=keywords
                    )
                    self.routes.append(route_data)

            # Traitement des waypoints
            for wpt in gpx.waypoints:
                # Extraire l'icône du waypoint
                icon = self.extract_waypoint_icon(wpt)

                waypoint_data = WaypointData(
                    file_path=file_path,
                    folder_path=folder_path,
                    name=wpt.name or os.path.basename(file_path),
                    waypoint=wpt,
                    keywords=keywords,
                    icon=icon
                )
                self.waypoints.append(waypoint_data)

        except Exception as e:
            print(f"[ERREUR] Impossible de traiter {file_path}: {e}")

    def process_folders(self, folders: List[str]) -> None:
        """Traite tous les fichiers GPX dans les dossiers spécifiés"""
        # Nettoyer complètement les données existantes
        self.tracks.clear()
        self.routes.clear()
        self.waypoints.clear()

        gpx_files = self.find_gpx_files(folders)
        for gpx_file in gpx_files:
            self.process_gpx_file(gpx_file, folders)

    def get_folder_colors(self) -> Dict[str, str]:
        """Génère un mapping couleur par dossier"""
        all_folders = set()
        for track in self.tracks:
            all_folders.add(track.folder_path)
        for route in self.routes:
            all_folders.add(route.folder_path)
        for wpt in self.waypoints:
            all_folders.add(wpt.folder_path)

        colors = ['blue', 'green', 'red', 'orange', 'purple',
                  'darkred', 'cadetblue', 'darkgreen', 'darkblue', 'pink']
        return {folder: colors[i % len(colors)] for i, folder in enumerate(sorted(all_folders))}


class MapRenderer:
    """Gestionnaire pour la génération et l'affichage des cartes"""

    def __init__(self, processor: GPXProcessor):
        self.processor = processor

    def geocode_location(self, location: str) -> Optional[Tuple[float, float]]:
        """Géocode une adresse ou un nom de lieu en coordonnées"""
        try:
            # Utilisation de l'API Nominatim (OpenStreetMap) - gratuite
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': location,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            }
            headers = {
                'User-Agent': 'GPX-Visualizer/1.0'
            }

            response = requests.get(
                url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data:
                    lat = float(data[0]['lat'])
                    lon = float(data[0]['lon'])
                    return (lat, lon)
        except Exception as e:
            print(f"[ERREUR] Géocodage échoué pour '{location}': {e}")
        return None

    def get_center_point(self) -> Tuple[float, float]:
        """Détermine le point central de la carte"""
        all_points = []

        for track in self.processor.tracks:
            if track.points:
                all_points.append(
                    (track.points[0].latitude, track.points[0].longitude))

        for route in self.processor.routes:
            if route.points:
                all_points.append(
                    (route.points[0].latitude, route.points[0].longitude))

        for wpt in self.processor.waypoints:
            all_points.append((wpt.waypoint.latitude, wpt.waypoint.longitude))

        if all_points:
            return all_points[0]
        return (0, 0)

    def create_map(self, show_tracks: bool = True, show_routes: bool = True, show_wpts: bool = True, search_location: str = None) -> folium.Map:
        """Crée une carte Folium avec les données GPX"""
        # Déterminer le centre de la carte
        if search_location:
            coords = self.geocode_location(search_location)
            if coords:
                center = coords
                zoom = 8  # Zoom plus large pour une vue d'ensemble
            else:
                center = self.get_center_point()
                zoom = 6  # Vue très large par défaut
        else:
            center = self.get_center_point()
            zoom = 6  # Vue très large par défaut

        m = folium.Map(location=center, zoom_start=zoom)

        if show_wpts:
            marker_cluster = MarkerCluster().add_to(m)

        color_map = self.processor.get_folder_colors()

        # Ajout des tracks
        if show_tracks:
            for track in self.processor.tracks:
                color = color_map.get(track.folder_path, 'blue')
                points = [(p.latitude, p.longitude) for p in track.points]
                if points:
                    folium.PolyLine(points, color=color, weight=3).add_to(m)

        # Ajout des routes
        if show_routes:
            for route in self.processor.routes:
                color = color_map.get(route.folder_path, 'blue')
                points = [(p.latitude, p.longitude) for p in route.points]
                if points:
                    folium.PolyLine(points, color=color,
                                    weight=2, dash_array='5').add_to(m)

        # Ajout des waypoints
        if show_wpts:
            for wpt in self.processor.waypoints:
                # Obtenir l'emoji approprié en utilisant l'icône ET le nom
                emoji = self.processor.get_emoji_for_icon(wpt.icon, wpt.name)

                # Créer le popup avec l'emoji
                popup_text = f"{emoji} {wpt.name}"

                # Créer un marqueur personnalisé avec l'emoji
                folium.Marker(
                    [wpt.waypoint.latitude, wpt.waypoint.longitude],
                    popup=popup_text,
                    icon=folium.DivIcon(
                        html=f'<div style="font-size: 20px; text-align: center;">{emoji}</div>',
                        icon_size=(20, 20),
                        icon_anchor=(10, 10)
                    )
                ).add_to(marker_cluster)

        return m

    def save_map(self, map_obj: folium.Map, output_path: str) -> None:
        """Sauvegarde la carte dans un fichier HTML"""
        map_obj.save(output_path)

    def generate_csv(self, output_path: str, show_tracks: bool = True, show_routes: bool = True, show_wpts: bool = True) -> None:
        """Génère un fichier CSV avec les données des traces"""
        with open(output_path, 'w', encoding='utf-8') as csvfile:
            csvfile.write(
                'name,type,length_m,elevation_gain,time_start,time_end,lat,lon,keywords\n')

            if show_tracks:
                for track in self.processor.tracks:
                    start_lat = track.points[0].latitude if track.points else ''
                    start_lon = track.points[0].longitude if track.points else ''
                    keywords_str = ','.join(track.keywords)
                    csvfile.write(
                        f'{track.name},track,{track.length:.2f},{track.elevation_gain:.2f},{track.start_time or ""},{track.end_time or ""},{start_lat},{start_lon},{keywords_str}\n')

            if show_routes:
                for route in self.processor.routes:
                    start_lat = route.points[0].latitude if route.points else ''
                    start_lon = route.points[0].longitude if route.points else ''
                    keywords_str = ','.join(route.keywords)
                    csvfile.write(
                        f'{route.name},route,{route.length:.2f},0,,,{start_lat},{start_lon},{keywords_str}\n')

            if show_wpts:
                for wpt in self.processor.waypoints:
                    keywords_str = ','.join(wpt.keywords)
                    csvfile.write(
                        f'{wpt.name},waypoint,0,0,,,{wpt.waypoint.latitude},{wpt.waypoint.longitude},{keywords_str}\n')


class DataManager:
    """Gestionnaire pour les données persistantes et le cache"""

    def __init__(self):
        self.state_file = os.path.join(
            tempfile.gettempdir(), "gpx_app_state.json")

    def load_last_folder(self) -> str:
        """Charge le dernier dossier utilisé"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                return state.get("last_folder", os.getcwd())
            except Exception:
                return os.getcwd()
        return os.getcwd()

    def save_last_folder(self, folder: str) -> None:
        """Sauvegarde le dernier dossier utilisé"""
        try:
            with open(self.state_file, "w") as f:
                json.dump({"last_folder": folder}, f)
        except Exception:
            pass


class TreeBuilder:
    """Gestionnaire pour la construction de l'arborescence des dossiers"""

    def __init__(self):
        pass

    def build_tree(self, root_dir: str) -> Dict:
        """Construit l'arborescence des dossiers"""
        tree = {"name": os.path.basename(
            root_dir), "path": root_dir, "children": []}
        try:
            entries = sorted(os.listdir(root_dir))
        except Exception:
            return tree
        for entry in entries:
            full_path = os.path.join(root_dir, entry)
            if os.path.isdir(full_path):
                tree["children"].append(self.build_tree(full_path))
        return tree

    def count_gpx_files(self, folder_path: str) -> int:
        """Compte les fichiers GPX dans un dossier"""
        try:
            return len([f for f in os.listdir(folder_path) if f.lower().endswith('.gpx')])
        except Exception:
            return 0

    def count_gpx_files_recursive(self, folder_path: str) -> int:
        """Compte récursivement tous les fichiers GPX dans un dossier et ses sous-dossiers"""
        count = 0
        try:
            # Compter les fichiers GPX dans le dossier courant
            count += self.count_gpx_files(folder_path)

            # Compter récursivement dans les sous-dossiers
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    count += self.count_gpx_files_recursive(item_path)
        except Exception:
            pass
        return count

    def render_tree(self, tree: Dict, selected: List[str], depth: int = 0) -> None:
        """Affiche l'arborescence avec des cases à cocher"""
        if not ST_AVAILABLE:
            return

        font_sizes = ["1.2em", "1.1em", "1.0em", "0.9em", "0.8em"]
        size = font_sizes[depth] if depth < len(font_sizes) else font_sizes[-1]

        count = self.count_gpx_files_recursive(tree["path"])
        indent = '\u00A0' * (depth * 4)
        label = f"{indent}{tree['name']} ({count})"

        # État initial basé sur la sélection actuelle
        initial = tree["path"] in selected
        checked = st.sidebar.checkbox(label, value=initial, key=tree["path"])

        # Gestion de la sélection/désélection
        if checked and tree["path"] not in selected:
            # Cocher : ajouter ce dossier et tous ses enfants
            selected.append(tree["path"])
            for child in tree.get("children", []):
                self._add_children_recursive(child, selected)
        elif not checked and tree["path"] in selected:
            # Décocher : retirer ce dossier et tous ses enfants
            selected.remove(tree["path"])
            for child in tree.get("children", []):
                self._remove_children_recursive(child, selected)

        # Rendu récursif des enfants
        for child in tree.get("children", []):
            self.render_tree(child, selected, depth=depth+1)

        # Après le rendu des enfants, vérifier si le parent doit être décoché
        # si aucun de ses enfants n'est sélectionné
        if tree.get("children") and tree["path"] in selected:
            has_selected_children = self._has_any_child_selected(
                tree, selected)
            if not has_selected_children:
                selected.remove(tree["path"])

    def _has_any_child_selected(self, tree: Dict, selected: List[str]) -> bool:
        """Vérifie si au moins un enfant est sélectionné"""
        if not tree.get("children"):
            return False

        for child in tree["children"]:
            if child["path"] in selected:
                return True
            # Vérifier récursivement les petits-enfants
            if self._has_any_child_selected(child, selected):
                return True
        return False

    def _add_children_recursive(self, child: Dict, selected: List[str]) -> None:
        """Ajoute récursivement tous les enfants à la sélection"""
        if child["path"] not in selected:
            selected.append(child["path"])
        for grandchild in child.get("children", []):
            self._add_children_recursive(grandchild, selected)

    def _remove_children_recursive(self, child: Dict, selected: List[str]) -> None:
        """Retire récursivement tous les enfants de la sélection"""
        if child["path"] in selected:
            selected.remove(child["path"])
        for grandchild in child.get("children", []):
            self._remove_children_recursive(grandchild, selected)

# ---------------------------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------------------------


class GPXApp:
    """Application principale pour la visualisation GPX"""

    def __init__(self):
        self.processor = GPXProcessor()
        self.map_renderer = MapRenderer(self.processor)
        self.data_manager = DataManager()
        self.tree_builder = TreeBuilder()

    def run_cli(self, folders: List[str], map_out: str, csv_out: str,
                show_tracks: bool, show_routes: bool, show_wpts: bool) -> int:
        """Exécute l'application en mode CLI"""
        self.processor.process_folders(folders)

        if not self.processor.tracks and not self.processor.routes and not self.processor.waypoints:
            print("[WARN] Aucun fichier GPX trouvé.")
            return 1

        # Génération de la carte
        map_obj = self.map_renderer.create_map(
            show_tracks, show_routes, show_wpts)
        self.map_renderer.save_map(map_obj, map_out)

        # Génération du CSV
        self.map_renderer.generate_csv(
            csv_out, show_tracks, show_routes, show_wpts)

        print(f"[INFO] Carte enregistrée dans {map_out}")
        print(f"[INFO] Récapitulatif CSV enregistré dans {csv_out}")
        return 0

    def run_streamlit_ui(self) -> None:
        """Exécute l'interface Streamlit"""
        if not ST_AVAILABLE:
            print("[ERREUR] Streamlit non disponible")
            return

        st.set_page_config(page_title="Bibliothèque GPX", layout="wide")
        st.title("📍 Bibliothèque GPX")

        # Volet gauche - Contrôles
        with st.sidebar:
            st.header("📁 Contenu")

            # Configuration du dossier
            last_folder = self.data_manager.load_last_folder()
            root_folder = st.text_input("Dossier racine", last_folder)

            if st.button("Charger l'arborescence", type="primary"):
                if not os.path.isdir(root_folder):
                    st.error(f"Dossier introuvable : {root_folder}")
                else:
                    self.data_manager.save_last_folder(root_folder)
                    tree = self.tree_builder.build_tree(root_folder)
                    st.session_state["tree"] = tree
                    st.session_state["selected"] = []
                    st.success("Arborescence chargée !")

            # Options d'affichage
            st.subheader("Options d'affichage")
            show_tracks = st.checkbox("Afficher les pistes", value=True)
            show_routes = st.checkbox("Afficher les routes", value=True)
            show_wpts = st.checkbox(
                "Afficher les points d'intérêt", value=True)

            # Arborescence des dossiers
            if "tree" in st.session_state:
                st.subheader("Arborescence des dossiers")
                self.tree_builder.render_tree(
                    st.session_state["tree"], st.session_state["selected"])

                if st.button("🗺️ Afficher la carte", type="secondary"):
                    if not st.session_state["selected"]:
                        st.error("Veuillez sélectionner au moins un dossier.")
                    else:
                        # Nettoyer et traiter les données
                        self.processor.process_folders(
                            st.session_state["selected"])

                        # Génération de la carte
                        map_obj = self.map_renderer.create_map(
                            show_tracks, show_routes, show_wpts)
                        self.map_renderer.save_map(
                            map_obj, "gpx_library_map.html")

                        # Génération du CSV
                        self.map_renderer.generate_csv(
                            "gpx_library_summary.csv", show_tracks, show_routes, show_wpts)

                        st.success("Carte et tableau générés !")
                        st.session_state["show_map"] = True

        # Zone principale - Affichage de la carte
        if st.session_state.get("show_map", False):
            # Recherche géographique discrète
            col1, col2 = st.columns([4, 1])

            with col1:
                search_location = st.text_input("",
                                                placeholder="Rechercher un lieu...",
                                                key="search_input",
                                                label_visibility="collapsed")

            with col2:
                if st.button("🔍", type="secondary", help="Rechercher et centrer sur ce lieu"):
                    if search_location:
                        # Retraiter les GPX pour s'assurer qu'ils sont affichés
                        self.processor.process_folders(
                            st.session_state["selected"])

                        # Régénérer la carte avec le nouveau centre
                        map_obj = self.map_renderer.create_map(
                            show_tracks, show_routes, show_wpts, search_location
                        )
                        self.map_renderer.save_map(
                            map_obj, "gpx_library_map.html")
                        st.success(f"Centré sur : {search_location}")
                        st.rerun()
                    else:
                        st.warning("Veuillez saisir un lieu")

            # Affichage de la carte
            try:
                with open("gpx_library_map.html", "r", encoding="utf-8") as f:
                    html_content = f.read()
                st.components.v1.html(html_content, height=600, scrolling=True)
            except Exception as e:
                st.error(f"Impossible d'afficher la carte : {e}")


def run_streamlit_ui():
    """Fonction de compatibilité pour l'ancienne interface"""
    app = GPXApp()
    app.run_streamlit_ui()

# ---------------------------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------------------------


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Bibliothèque GPX locale — Mode CLI")
    p.add_argument("--folder", default=None, help="Dossier contenant les .gpx")
    p.add_argument("--map-out", default="gpx_library_map.html")
    p.add_argument("--csv-out", default="gpx_library_summary.csv")
    p.add_argument("--no-tracks", action="store_true")
    p.add_argument("--no-routes", action="store_true")
    p.add_argument("--no-wpts", action="store_true")
    p.add_argument("--test", action="store_true")
    return p.parse_args(list(argv))


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    if args.test:
        print("[TEST] OK")
        sys.exit(0)

    app = GPXApp()

    if ST_AVAILABLE:
        app.run_streamlit_ui()
    else:
        if not args.folder:
            print("[ERREUR] Vous devez préciser --folder en mode CLI.",
                  file=sys.stderr)
            sys.exit(1)
        sys.exit(
            app.run_cli(
                folders=[args.folder],
                map_out=args.map_out,
                csv_out=args.csv_out,
                show_tracks=not args.no_tracks,
                show_routes=not args.no_routes,
                show_wpts=not args.no_wpts,
            )
        )
