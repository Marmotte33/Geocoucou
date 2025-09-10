# app.py — Bibliothèque GPX locale (lecture d'un dossier et affichage sur carte)
import os
import sys
import argparse
import datetime as dt
import tempfile
import json
import glob
import random

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
except ModuleNotFoundError as e:
    print("[ERREUR] Modules requis manquants (gpxpy, folium).", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------------------------
# Fonctions pour lire les GPX et générer la carte
# ---------------------------------------------------------------------------------------------

def find_gpx_files(folder: str, recursive: bool) -> list:
    pattern = '**/*.gpx' if recursive else '*.gpx'
    search_path = os.path.join(folder, pattern)
    return [f for f in glob.glob(search_path, recursive=recursive) if os.path.isfile(f)]

def get_folder_colors(gpx_files: list) -> dict:
    # Chaque dossier unique a sa couleur assignée
    unique_folders = list(set(os.path.dirname(f) for f in gpx_files))
    colors = ['blue', 'green', 'red', 'orange', 'purple', 'darkred', 'cadetblue', 'darkgreen', 'darkblue', 'pink']
    color_map = {folder: colors[i % len(colors)] for i, folder in enumerate(unique_folders)}
    return color_map

STATE_FILE = os.path.join(tempfile.gettempdir(), "gpx_app_state.json")

def load_last_folder() -> str:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            return state.get("last_folder", os.getcwd())
        except Exception:
            return os.getcwd()
    return os.getcwd()

def save_last_folder(folder: str):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_folder": folder}, f)
    except Exception:
        pass

def run_cli(folder: str, recursive: bool, map_out: str, csv_out: str, show_tracks: bool, show_routes: bool, show_wpts: bool) -> int:
    gpx_files = find_gpx_files(folder, recursive)
    if not gpx_files:
        print("[WARN] Aucun fichier GPX trouvé.")
        return 1

    color_map = get_folder_colors(gpx_files)

    first_point = None
    for gpx_file in gpx_files:
        with open(gpx_file, 'r', encoding='utf-8') as f:
            gpx = gpxpy.parse(f)
            for track in gpx.tracks:
                for segment in track.segments:
                    if segment.points:
                        first_point = (segment.points[0].latitude, segment.points[0].longitude)
                        break
                if first_point:
                    break
            if first_point:
                break

    if not first_point:
        first_point = (0,0)

    m = folium.Map(location=first_point, zoom_start=12)
    marker_cluster = MarkerCluster().add_to(m)

    with open(csv_out, 'w', encoding='utf-8') as csvfile:
        csvfile.write('name,type,length_m,time_start,time_end,lat,lon\n')

        for gpx_file in gpx_files:
            folder_path = os.path.dirname(gpx_file)
            color = color_map.get(folder_path, 'blue')

            with open(gpx_file, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)

            if show_tracks:
                for track in gpx.tracks:
                    for segment in track.segments:
                        points = [(p.latitude, p.longitude) for p in segment.points]
                        if points:
                            folium.PolyLine(points, color=color, weight=3).add_to(m)
                    bounds = track.get_time_bounds()
                    start_time = bounds.start_time.isoformat() if bounds and bounds.start_time else ''
                    end_time = bounds.end_time.isoformat() if bounds and bounds.end_time else ''
                    csvfile.write(f'{os.path.basename(gpx_file)},track,{track.length_3d():.2f},{start_time},{end_time},,\n')

            if show_routes:
                for route in gpx.routes:
                    points = [(p.latitude, p.longitude) for p in route.points]
                    if points:
                        folium.PolyLine(points, color=color, weight=2, dash_array='5').add_to(m)
                    length = sum(p.distance_3d(route.points[i-1]) if i>0 else 0 for i,p in enumerate(route.points))
                    csvfile.write(f'{os.path.basename(gpx_file)},route,{length:.2f},,,\n')

            if show_wpts:
                for wpt in gpx.waypoints:
                    folium.Marker([wpt.latitude, wpt.longitude], popup=wpt.name or '').add_to(marker_cluster)
                    csvfile.write(f'{os.path.basename(gpx_file)},waypoint,,,{wpt.latitude},{wpt.longitude}\n')

    m.save(map_out)
    print(f"[INFO] Carte enregistrée dans {map_out}")
    print(f"[INFO] Récapitulatif CSV enregistré dans {csv_out}")
    return 0

def run_streamlit_ui():
    st.set_page_config(page_title="Bibliothèque GPX", layout="wide")
    st.title("📍 Bibliothèque GPX locale")

    last_folder = load_last_folder()
    folder = st.text_input("Chemin du dossier", last_folder)

    recursive = st.checkbox("Parcourir les sous-dossiers", value=True)
    show_tracks = st.checkbox("Afficher les pistes", value=True)
    show_routes = st.checkbox("Afficher les routes", value=True)
    show_wpts = st.checkbox("Afficher les points d'intérêt", value=True)

    if st.button("Charger le dossier"):
        if not os.path.isdir(folder):
            st.error(f"Dossier introuvable : {folder}")
            return
        save_last_folder(folder)
        run_cli(
            folder=folder,
            recursive=recursive,
            map_out="gpx_library_map.html",
            csv_out="gpx_library_summary.csv",
            show_tracks=show_tracks,
            show_routes=show_routes,
            show_wpts=show_wpts,
        )
        st.success("Carte et tableau générés !")

        try:
            with open("gpx_library_map.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            components.html(html_content, height=600, scrolling=True)
        except Exception as e:
            st.error(f"Impossible d'afficher la carte : {e}")

def parse_args(argv):
    p = argparse.ArgumentParser(description="Bibliothèque GPX locale — Mode CLI")
    p.add_argument("--folder", default=None, help="Dossier contenant les .gpx")
    p.add_argument("--recursive", action="store_true")
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

    if ST_AVAILABLE:
        run_streamlit_ui()
    else:
        if not args.folder:
            print("[ERREUR] Vous devez préciser --folder en mode CLI.", file=sys.stderr)
            sys.exit(1)
        sys.exit(
            run_cli(
                folder=args.folder,
                recursive=args.recursive,
                map_out=args.map_out,
                csv_out=args.csv_out,
                show_tracks=not args.no_tracks,
                show_routes=not args.no_routes,
                show_wpts=not args.no_wpts,
            )
        )
