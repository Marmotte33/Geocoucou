# app.py — Bibliothèque GPX locale (lecture d'un dossier et affichage sur carte)
import os
import sys
import argparse
import tempfile
import json

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
# Fonctions utilitaires
# ---------------------------------------------------------------------------------------------

def find_gpx_files(folders: list) -> list:
    gpx_files = []
    for folder in folders:
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".gpx"):
                    gpx_files.append(os.path.join(root, f))
    return gpx_files

def get_folder_colors(gpx_files: list) -> dict:
    unique_folders = list(set(os.path.dirname(f) for f in gpx_files))
    colors = ['blue','green','red','orange','purple','darkred','cadetblue','darkgreen','darkblue','pink']
    return {folder: colors[i % len(colors)] for i, folder in enumerate(unique_folders)}

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

# ---------------------------------------------------------------------------------------------
# Fonction de génération de la carte et du CSV
# ---------------------------------------------------------------------------------------------

def run_cli(folders: list, map_out: str, csv_out: str, show_tracks: bool, show_routes: bool, show_wpts: bool) -> int:
    gpx_files = find_gpx_files(folders)
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
            if folder_path not in folders:
                continue  # Ne charger que les dossiers sélectionnés

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
                    csvfile.write(f'{os.path.basename(gpx_file)},track,{track.length_3d():.2f},{start_time},{end_time},,\\n')

            if show_routes:
                for route in gpx.routes:
                    points = [(p.latitude, p.longitude) for p in route.points]
                    if points:
                        folium.PolyLine(points, color=color, weight=2, dash_array='5').add_to(m)
                    length = sum(p.distance_3d(route.points[i-1]) if i>0 else 0 for i,p in enumerate(route.points))
                    csvfile.write(f'{os.path.basename(gpx_file)},route,{length:.2f},,,\\n')

            if show_wpts:
                for wpt in gpx.waypoints:
                    folium.Marker([wpt.latitude, wpt.longitude], popup=wpt.name or '').add_to(marker_cluster)
                    csvfile.write(f'{os.path.basename(gpx_file)},waypoint,,,{wpt.latitude},{wpt.longitude}\\n')

    m.save(map_out)
    print(f"[INFO] Carte enregistrée dans {map_out}")
    print(f"[INFO] Récapitulatif CSV enregistré dans {csv_out}")
    return 0

# ---------------------------------------------------------------------------------------------
# UI Streamlit avec arborescence et cases à cocher
# ---------------------------------------------------------------------------------------------

def build_tree(root_dir):
    tree = {"name": os.path.basename(root_dir), "path": root_dir, "children": []}
    try:
        entries = sorted(os.listdir(root_dir))
    except Exception:
        return tree
    for entry in entries:
        full_path = os.path.join(root_dir, entry)
        if os.path.isdir(full_path):
            tree["children"].append(build_tree(full_path))
    return tree


def count_gpx_files(folder_path):
    return len([f for f in os.listdir(folder_path) if f.lower().endswith('.gpx')])


def render_tree(tree, selected, depth=0):
    font_sizes = ["1.2em", "1.1em", "1.0em", "0.9em", "0.8em"]
    size = font_sizes[depth] if depth < len(font_sizes) else font_sizes[-1]

    count = count_gpx_files(tree["path"])
    indent = '\u00A0' * (depth * 4)
    label = f"{indent}{tree['name']} ({count})"

    initial = tree["path"] in selected
    checked = st.sidebar.checkbox(label, value=initial, key=tree["path"])

    if checked:
        if tree["path"] not in selected:
            selected.append(tree["path"])
        for child in tree.get("children", []):
            def add_child(c):
                if c["path"] not in selected:
                    selected.append(c["path"])
                for gc in c.get("children", []):
                    add_child(gc)
            add_child(child)

    if not checked and tree["path"] in selected:
        selected.remove(tree["path"])
        for child in tree.get("children", []):
            def remove_child(c):
                if c["path"] in selected:
                    selected.remove(c["path"])
                for gc in c.get("children", []):
                    remove_child(gc)
            remove_child(child)

    for child in tree.get("children", []):
        render_tree(child, selected, depth=depth+1)


def run_streamlit_ui():
    st.set_page_config(page_title="Bibliothèque GPX", layout="wide")
    st.title("📍 Bibliothèque GPX locale")

    last_folder = load_last_folder()
    root_folder = st.text_input("Dossier racine", last_folder)

    show_tracks = st.checkbox("Afficher les pistes", value=True)
    show_routes = st.checkbox("Afficher les routes", value=True)
    show_wpts = st.checkbox("Afficher les points d'intérêt", value=True)

    if st.button("Charger l'arborescence"):
        if not os.path.isdir(root_folder):
            st.error(f"Dossier introuvable : {root_folder}")
            return
        save_last_folder(root_folder)
        tree = build_tree(root_folder)
        st.session_state["tree"] = tree
        st.session_state["selected"] = []

    if "tree" in st.session_state:
        st.sidebar.header("Arborescence des dossiers")
        render_tree(st.session_state["tree"], st.session_state["selected"])

        if st.sidebar.button("Afficher la carte"):
            if not st.session_state["selected"]:
                st.sidebar.error("Veuillez sélectionner au moins un dossier.")
                return
            run_cli(
                folders=st.session_state["selected"],
                map_out="gpx_library_map.html",
                csv_out="gpx_library_summary.csv",
                show_tracks=show_tracks,
                show_routes=show_routes,
                show_wpts=show_wpts,
            )
            st.sidebar.success("Carte et tableau générés !")
            try:
                with open("gpx_library_map.html", "r", encoding="utf-8") as f:
                    html_content = f.read()
                st.components.v1.html(html_content, height=600, scrolling=True)
            except Exception as e:
                st.sidebar.error(f"Impossible d'afficher la carte : {e}")

# ---------------------------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(description="Bibliothèque GPX locale — Mode CLI")
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

    if ST_AVAILABLE:
        run_streamlit_ui()
    else:
        if not args.folder:
            print("[ERREUR] Vous devez préciser --folder en mode CLI.", file=sys.stderr)
            sys.exit(1)
        sys.exit(
            run_cli(
                folders=[args.folder],
                map_out=args.map_out,
                csv_out=args.csv_out,
                show_tracks=not args.no_tracks,
                show_routes=not args.no_routes,
                show_wpts=not args.no_wpts,
            )
        )
