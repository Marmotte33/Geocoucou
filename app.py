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
    import plotly.graph_objects as go
    import math
except ModuleNotFoundError as e:
    print("[ERREUR] Modules requis manquants (gpxpy, folium, plotly).",
          file=sys.stderr)
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

    @property
    def lat(self) -> float:
        return self.waypoint.latitude

    @property
    def lon(self) -> float:
        return self.waypoint.longitude

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
            return None

    def get_emoji_for_icon(self, icon: str, waypoint_name: str = "") -> str:
        """Convertit une icône GPX en emoji approprié, en utilisant aussi le nom du waypoint"""
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
            'fromage': '🧀', 'cheese': '🧀', 'fromagerie': '🧀',

            # Icônes spécifiques aux applications de cartographie
            'osmand': '🗺️', 'garmin': '⌚', 'strava': '🏃',
            'waypoint': '📍', 'waypoints': '📍', 'wpt': '📍',
            'poi': '📍', 'point_of_interest': '📍',
            'marker': '📍', 'pin': '📍', 'location': '📍',
            'place': '📍', 'spot': '📍', 'site': '📍',

            # Icônes de navigation
            'north': '🧭', 'south': '🧭', 'east': '🧭', 'west': '🧭',
            'compass': '🧭', 'direction': '🧭', 'bearing': '🧭',
            'route': '🛣️', 'road': '🛣️', 'path': '🛣️', 'trail': '🛣️',
            'track': '🛤️', 'railway': '🛤️', 'rail': '🛤️',

            # Icônes de météo et conditions
            'sunny': '☀️', 'sun': '☀️', 'clear': '☀️',
            'cloudy': '☁️', 'cloud': '☁️', 'overcast': '☁️',
            'rainy': '🌧️', 'rain': '🌧️', 'precipitation': '🌧️',
            'snowy': '❄️', 'snow': '❄️', 'winter': '❄️',
            'windy': '💨', 'wind': '💨', 'breeze': '💨',
            'storm': '⛈️', 'thunderstorm': '⛈️', 'lightning': '⛈️',

            # Icônes de temps et horaires
            'time': '⏰', 'clock': '⏰', 'hour': '⏰',
            'schedule': '📅', 'calendar': '📅', 'date': '📅',
            'open': '🟢', 'closed': '🔴', 'available': '🟢',
            'busy': '🔴', 'occupied': '🔴', 'free': '🟢',

            # Icônes de qualité et évaluation
            'excellent': '⭐', 'good': '👍', 'average': '👌',
            'poor': '👎', 'bad': '👎', 'terrible': '👎',
            'recommended': '👍', 'favorite': '❤️', 'best': '🏆',
            'worst': '💩', 'avoid': '❌', 'skip': '⏭️',

            # Icônes de taille et quantité
            'large': '🔵', 'big': '🔵', 'huge': '🔵',
            'small': '🔸', 'tiny': '🔸', 'mini': '🔸',
            'medium': '🔶', 'average': '🔶', 'normal': '🔶',
            'many': '🔢', 'few': '🔢', 'several': '🔢',

            # Icônes de statut et état
            'new': '🆕', 'old': '🆕', 'ancient': '🆕',
            'modern': '🆕', 'contemporary': '🆕', 'historic': '🏛️',
            'temporary': '⏳', 'permanent': '♾️', 'seasonal': '🍂',
            'year_round': '♾️', 'summer': '☀️', 'winter': '❄️',

            # Icônes de direction et orientation
            'up': '⬆️', 'down': '⬇️', 'left': '⬅️', 'right': '➡️',
            'forward': '⬆️', 'backward': '⬇️', 'straight': '⬆️',
            'turn': '↩️', 'curve': '↩️', 'bend': '↩️',
            'junction': '➕', 'intersection': '➕', 'crossing': '➕',

            # Icônes de surface et terrain
            'paved': '🛣️', 'unpaved': '🛤️', 'dirt': '🛤️',
            'gravel': '🛤️', 'sand': '🏖️', 'rock': '🪨',
            'mud': '🟤', 'wet': '💧', 'dry': '🏜️',
            'smooth': '🛣️', 'rough': '🛤️', 'bumpy': '🛤️',

            # Icônes de difficulté et niveau
            'easy': '🟢', 'medium': '🟡', 'hard': '🔴', 'difficult': '🔴',
            'beginner': '🟢', 'intermediate': '🟡', 'advanced': '🔴',
            'expert': '🔴', 'professional': '🔴', 'amateur': '🟢',
            'family': '👨‍👩‍👧‍👦', 'children': '👶', 'adult': '👤',

            # Icônes de sécurité et réglementation
            'safe': '✅', 'unsafe': '❌', 'dangerous': '⚠️',
            'restricted': '🚫', 'forbidden': '🚫', 'prohibited': '🚫',
            'allowed': '✅', 'permitted': '✅', 'legal': '✅',
            'illegal': '❌', 'private': '🔒', 'public': '🔓',

            # Icônes de coût et prix
            'free': '🆓', 'paid': '💰', 'expensive': '💸',
            'cheap': '💵', 'affordable': '💵', 'budget': '💵',
            'luxury': '💎', 'premium': '💎', 'deluxe': '💎',
            'discount': '🏷️', 'sale': '🏷️', 'offer': '🏷️'
        }

        # 1. PRIORITÉ : Recherche basée sur l'icône GPX uniquement
        if icon:
            icon_clean = icon.lower().replace('_', ' ').replace('-', ' ').replace(',', ' ')
            for key, emoji in icon_mapping.items():
                if key in icon_clean or icon_clean in key:
                    return emoji

        # 2. FALLBACK : Recherche dans le nom du waypoint (en dernier recours)
        if waypoint_name:
            name_words = waypoint_name.lower().split()
            for word in name_words:
                # Nettoyer le mot (enlever ponctuation)
                clean_word = ''.join(c for c in word if c.isalnum())
                for key, emoji in icon_mapping.items():
                    if clean_word == key or key in clean_word:
                        return emoji

        # 3. DÉFAUT : Emoji générique
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

    def get_gpx_colors(self) -> Dict[str, str]:
        """Génère un mapping couleur par fichier GPX"""
        all_gpx_files = set()
        for track in self.tracks:
            all_gpx_files.add(track.file_path)
        for route in self.routes:
            all_gpx_files.add(route.file_path)
        for wpt in self.waypoints:
            all_gpx_files.add(wpt.file_path)

        colors = ['blue', 'green', 'red', 'orange', 'purple',
                  'darkred', 'lightred', 'beige', 'darkblue', 'darkgreen',
                  'cadetblue', 'darkpurple', 'white', 'pink', 'lightblue',
                  'lightgreen', 'gray', 'black', 'lightgray', 'darkorange',
                  'lime', 'teal', 'navy', 'maroon', 'olive', 'aqua', 'fuchsia']
        return {gpx_file: colors[i % len(colors)] for i, gpx_file in enumerate(sorted(all_gpx_files))}


class MapRenderer:
    """Gestionnaire pour la génération et l'affichage des cartes"""

    def __init__(self, processor: GPXProcessor):
        self.processor = processor

    def calculate_elevation_profile_from_gpx(self, gpx_file_path: str) -> tuple:
        """Calcule le profil altitude/distance à partir d'un fichier GPX avec gpxpy"""
        try:
            with open(gpx_file_path, 'r', encoding='utf-8') as gpx_file:
                gpx = gpxpy.parse(gpx_file)

            distances = [0.0]  # Distance cumulative en km
            elevations = []    # Altitudes en m

            # Parcourir toutes les traces (trk)
            for track in gpx.tracks:
                for segment in track.segments:
                    for i, point in enumerate(segment.points):
                        # Récupérer l'altitude (ele)
                        elevation = point.elevation if point.elevation is not None else 0.0
                        elevations.append(elevation)

                        # Calculer la distance cumulative (sauf pour le premier point)
                        if i > 0:
                            prev_point = segment.points[i-1]
                            # Utiliser la méthode distance_2d de gpxpy
                            distance_km = prev_point.distance_2d(
                                point) / 1000  # Conversion m -> km
                            distances.append(distances[-1] + distance_km)

            return distances, elevations

        except Exception as e:
            print(f"Erreur lors du calcul du profil : {e}")
            return [], []

    def create_elevation_chart(self, gpx_file_path: str) -> go.Figure:
        """Crée un graphique altitude/distance à partir d'un fichier GPX"""
        distances, elevations = self.calculate_elevation_profile_from_gpx(
            gpx_file_path)

        if not distances or not elevations:
            # Graphique vide si pas de données
            fig = go.Figure()
            fig.add_annotation(
                text="Aucune donnée d'altitude disponible",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(
                title="Profil altitude/distance",
                xaxis_title="Distance (km)",
                yaxis_title="Altitude (m)",
                height=300
            )
            return fig

        # Créer le graphique
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=distances,
            y=elevations,
            mode='lines',
            name='Altitude',
            line=dict(color='blue', width=2),
            fill='tonexty'
        ))

        fig.update_layout(
            title="Profil altitude/distance",
            xaxis_title="Distance (km)",
            yaxis_title="Altitude (m)",
            height=300,
            margin=dict(l=50, r=50, t=50, b=50),
            showlegend=False
        )

        return fig

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

    def create_map(self, show_tracks: bool = True, show_routes: bool = True, show_wpts: bool = True, search_location: str = None, cluster_waypoints: bool = True, color_per_gpx: bool = False) -> folium.Map:
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
            if cluster_waypoints:
                # Configuration du cluster pour afficher les waypoints individuels plus tôt
                marker_cluster = MarkerCluster(
                    # Rayon maximum pour l'agrégation (en pixels)
                    max_cluster_radius=50,
                    disable_clustering_at_zoom=10,  # Zoom à partir duquel on n'agrège plus
                    spiderfy_on_max_zoom=True,  # Séparer les marqueurs au zoom max
                    show_coverage_on_hover=False,  # Ne pas montrer la zone de couverture
                    zoom_to_bounds_on_click=True  # Zoomer sur les bounds du cluster
                ).add_to(m)
            else:
                # Pas de clustering - tous les waypoints visibles individuellement
                marker_cluster = m

        # Choisir le type de coloration selon l'option
        if color_per_gpx:
            color_map = self.processor.get_gpx_colors()
        else:
            color_map = self.processor.get_folder_colors()

        # Ajout des tracks
        if show_tracks:
            for track in self.processor.tracks:
                if color_per_gpx:
                    color = color_map.get(track.file_path, 'blue')
                else:
                    color = color_map.get(track.folder_path, 'blue')
                points = [(p.latitude, p.longitude) for p in track.points]
                if points:
                    # Créer un popup avec le nom du fichier GPX
                    popup_text = f"<b>Trace:</b> {track.name}<br><b>Dossier:</b> {os.path.basename(track.folder_path)}"
                    folium.PolyLine(points, color=color, weight=3,
                                    popup=folium.Popup(popup_text, max_width=300)).add_to(m)

        # Ajout des routes
        if show_routes:
            for route in self.processor.routes:
                if color_per_gpx:
                    color = color_map.get(route.file_path, 'blue')
                else:
                    color = color_map.get(route.folder_path, 'blue')
                points = [(p.latitude, p.longitude) for p in route.points]
                if points:
                    # Créer un popup avec le nom du fichier GPX
                    popup_text = f"<b>Route:</b> {route.name}<br><b>Dossier:</b> {os.path.basename(route.folder_path)}"
                    folium.PolyLine(points, color=color, weight=2, dash_array='5',
                                    popup=folium.Popup(popup_text, max_width=300)).add_to(m)

        # Ajout des waypoints
        if show_wpts:
            for wpt in self.processor.waypoints:
                # Obtenir l'emoji approprié en utilisant l'icône ET le nom
                emoji = self.processor.get_emoji_for_icon(wpt.icon, wpt.name)

                # Créer le popup avec l'emoji
                popup_text = f"{emoji} {wpt.name}"

                # Créer un marqueur personnalisé avec l'emoji
                folium.Marker(
                    [wpt.lat, wpt.lon],
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
            show_tracks, show_routes, show_wpts, color_per_gpx=False)
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
        st.title("GEOCOUCOU")

        # Volet gauche - Contrôles
        with st.sidebar:
            st.header("Contenu")

            # Configuration du dossier
            last_folder = self.data_manager.load_last_folder()
            root_folder = st.text_input("Dossier racine", last_folder)

            if st.button("📁 Charger l'arborescence", type="secondary"):
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

            # Option pour la coloration
            color_per_gpx = st.checkbox("Une couleur par GPX", value=False,
                                        help="Si coché, chaque fichier GPX aura sa propre couleur. Sinon, une couleur par dossier.")

            # Option pour contrôler l'agrégation des waypoints
            if show_wpts:
                st.session_state["cluster_waypoints"] = st.checkbox(
                    "Agréger les waypoints (bulles de regroupement)",
                    value=True,
                    help="Désactivez pour voir tous les waypoints individuellement même au zoom faible"
                )

            # Arborescence des dossiers
            if "tree" in st.session_state:
                st.subheader("Arborescence")
                self.tree_builder.render_tree(
                    st.session_state["tree"], st.session_state["selected"])

                if st.button("🗺️ Afficher la carte", type="secondary"):
                    if not st.session_state["selected"]:
                        st.error("Veuillez sélectionner au moins un dossier.")
                    else:
                        # Nettoyer et traiter les données
                        self.processor.process_folders(
                            st.session_state["selected"])

                        # Sauvegarder les données dans session_state pour le bandeau
                        st.session_state["tracks_data"] = self.processor.tracks
                        st.session_state["routes_data"] = self.processor.routes
                        st.session_state["waypoints_data"] = self.processor.waypoints

                        # Génération de la carte
                        cluster_waypoints = st.session_state.get(
                            "cluster_waypoints", True)
                        map_obj = self.map_renderer.create_map(
                            show_tracks, show_routes, show_wpts, cluster_waypoints=cluster_waypoints, color_per_gpx=color_per_gpx)
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

                        # Sauvegarder les données dans session_state pour le bandeau
                        st.session_state["tracks_data"] = self.processor.tracks
                        st.session_state["routes_data"] = self.processor.routes
                        st.session_state["waypoints_data"] = self.processor.waypoints

                        # Régénérer la carte avec le nouveau centre
                        cluster_waypoints = st.session_state.get(
                            "cluster_waypoints", True)
                        map_obj = self.map_renderer.create_map(
                            show_tracks, show_routes, show_wpts, search_location, cluster_waypoints=cluster_waypoints, color_per_gpx=color_per_gpx
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

            # Bandeau horizontal pour le profil d'altitude (séparé de la carte)
            st.markdown("---")
            st.markdown("### 📈 Profil d'altitude")

            # Interface de sélection du GPX
            col1, col2 = st.columns([4, 1])

            with col1:
                # Dropdown avec la liste des traces chargées
                tracks_data = st.session_state.get("tracks_data", [])
                if tracks_data:
                    # Regrouper par nom de fichier pour éviter les doublons
                    unique_tracks = {}
                    for track in tracks_data:
                        if track.name not in unique_tracks:
                            unique_tracks[track.name] = track

                    track_names = list(unique_tracks.keys())
                    selected_track = st.selectbox(
                        "",
                        options=[""] + track_names,
                        help="Choisissez une trace dans la liste des GPX chargés",
                        label_visibility="collapsed",
                        placeholder="Sélectionner une trace GPX..."
                    )
                    st.session_state["selected_track_for_profile"] = selected_track
                else:
                    st.info(
                        "Aucune trace GPX chargée. Chargez d'abord des dossiers.")
                    selected_track = ""

            with col2:
                # Bouton pour charger le profil
                if st.button("🔄 Charger le profil", type="secondary", disabled=not selected_track):
                    if selected_track:
                        st.session_state["load_profile"] = True
                        st.session_state["profile_track_name"] = selected_track

            # Afficher le profil seulement si demandé
            if st.session_state.get("load_profile", False) and st.session_state.get("profile_track_name"):
                track_name = st.session_state["profile_track_name"]
                st.markdown(f"*Trace : {track_name}*")

                # Utiliser les données sauvegardées
                tracks_data = st.session_state.get("tracks_data", [])

                # Regrouper par nom de fichier (même logique que le dropdown)
                unique_tracks = {}
                for track in tracks_data:
                    if track.name not in unique_tracks:
                        unique_tracks[track.name] = track

                # Trouver le fichier GPX correspondant à la trace sélectionnée
                selected_track_obj = unique_tracks.get(track_name)

                if selected_track_obj:
                    # Utiliser le fichier GPX de la trace sélectionnée
                    gpx_file_path = selected_track_obj.file_path

                    try:
                        # Créer et afficher le graphique
                        chart = self.map_renderer.create_elevation_chart(
                            gpx_file_path)
                        st.plotly_chart(chart, use_container_width=True)

                        # Afficher quelques statistiques
                        distances, elevations = self.map_renderer.calculate_elevation_profile_from_gpx(
                            gpx_file_path)
                        if distances and elevations:
                            max_elevation = max(elevations)
                            min_elevation = min(elevations)
                            total_distance = distances[-1] if distances else 0

                            # Calculer le dénivelé positif cumulé
                            elevation_gain = sum(
                                max(0, elevations[i] - elevations[i-1]) for i in range(1, len(elevations)))

                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Distance totale",
                                          f"{total_distance:.1f} km")
                            with col2:
                                st.metric("Altitude max",
                                          f"{max_elevation:.0f} m")
                            with col3:
                                st.metric("Altitude min",
                                          f"{min_elevation:.0f} m")
                            with col4:
                                st.metric("Dénivelé positif",
                                          f"{elevation_gain:.0f} m")

                    except Exception as e:
                        st.error(
                            f"Erreur lors de la lecture du fichier GPX : {e}")
                        st.info(
                            "Vérifiez que le fichier existe et est accessible")
                else:
                    st.error("Trace non trouvée dans les données chargées")

                # Bouton pour masquer le profil
                if st.button("❌ Masquer le profil", type="secondary"):
                    st.session_state["load_profile"] = False
                    st.rerun()


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
