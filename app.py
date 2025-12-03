import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
import streamlit.components.v1 as components

try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False
    st.warning("Folium ni na voljo. Namestite ga z: pip install folium streamlit-folium")

epsgs = {
    "WGS 84 (EPSG:4326)": {
        "code": 4326, 
        "x_label": "Lon", 
        "y_label": "Lat",
        "x_name": "Longitude",
        "y_name": "Latitude"
    },
    "Gauss (EPSG:3912)": {
        "code": 3912, 
        "x_label": "GKX", 
        "y_label": "GKY",
        "x_name": "GKX (sever)",
        "y_name": "GKY (vzhod)"
    },
    "D96 (EPSG:3794)": {
        "code": 3794, 
        "x_label": "E", 
        "y_label": "N",
        "x_name": "E (east)",
        "y_name": "N (north)"
    },
}

def parse_data_with_headers(text):
    """Parse podatkov z glavami stolpcev - prva vrstica so imena stolpcev"""
    lines = text.strip().split('\n')
    if not lines:
        return None, []
    
    # Prva vrstica so imena stolpcev
    header_line = lines[0].strip()
    if '\t' in header_line:
        headers = header_line.split('\t')
    elif ';' in header_line:
        headers = header_line.split(';')
    else:
        headers = header_line.split()
    
    data_rows = []
    for i, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
            
        # Ločitev podatkov
        if '\t' in line:
            parts = line.split('\t')
        elif ';' in line:
            parts = line.split(';')
        else:
            parts = line.split()
            
        if len(parts) >= len(headers):
            row_data = {'row_id': i-1}
            for j, header in enumerate(headers):
                if j < len(parts):
                    row_data[header] = parts[j]
            data_rows.append(row_data)
        else:
            st.warning(f"Vrstica {i}: '{line}' - premalo stolpcev")
    
    return headers, data_rows

def convert_coordinates_from_data(data_rows, x_col, y_col, from_epsg, to_epsg):
    """Pretvori koordinate iz podatkov z določenimi stolpci"""
    if from_epsg == to_epsg:
        return data_rows
    
    if not data_rows:
        return []
    
    try:
        points = []
        for row in data_rows:
            try:
                x_val = float(row[x_col])
                y_val = float(row[y_col])
                
                # Za Gauss (3912) zamenjaj X in Y, ker je Y vodoravna os, X pa navpična
                if from_epsg == 3912:
                    # GKY je vodoravno (vzhod), GKX je navpično (sever)
                    # V geopandas Point(x, y) pomeni Point(vzhod, sever)
                    points.append(Point(x_val, y_val))  # GKY je že vzhod, GKX je že sever
                else:
                    points.append(Point(x_val, y_val))
                    
            except (ValueError, KeyError):
                points.append(None)
        
        # Ustvari DataFrame
        df = pd.DataFrame(data_rows)
        
        # Ustvari GeoDataFrame z geometrijo
        gdf = gpd.GeoDataFrame(df, geometry=points, crs=f"EPSG:{from_epsg}")
        
        # Odstrani vrstice z None geometrijo
        gdf = gdf.dropna(subset=['geometry'])
        
        # Pretvori v ciljni koordinatni sistem
        gdf_transformed = gdf.to_crs(f"EPSG:{to_epsg}")
        
        # Dodaj nove koordinate v DataFrame
        gdf_transformed['converted_x'] = gdf_transformed.geometry.x
        gdf_transformed['converted_y'] = gdf_transformed.geometry.y
        
        # Za Gauss (3912) na izhodu obrni koordinate nazaj
        if to_epsg == 3912:
            # Na izhodu: geografski X postane GKX, geografski Y postane GKY
            gdf_transformed['converted_x'] = gdf_transformed.geometry.y  # sever -> GKX
            gdf_transformed['converted_y'] = gdf_transformed.geometry.x  # vzhod -> GKY
        
        return gdf_transformed.to_dict('records')
        
    except Exception as e:
        st.error(f"Napaka pri pretvorbi koordinat: {e}")
        return []

def prepare_folium_data(dataset1_data, x_col_1, y_col_1, coord_system_1, display_columns_1,
                       dataset2_data, x_col_2, y_col_2, coord_system_2, display_columns_2):
    """Pripravi podatke za Folium zemljevid z interaktivnimi popup-i"""
    
    all_points = []
    
    # Prvi niz podatkov
    if dataset1_data and x_col_1 and y_col_1 and coord_system_1:
        converted_data_1 = convert_coordinates_from_data(
            dataset1_data, x_col_1, y_col_1, 
            epsgs[coord_system_1]["code"], 4326
        )
        
        for i, row in enumerate(converted_data_1):
            if 'converted_x' in row and 'converted_y' in row:
                # Pripravi popup text
                popup_parts = [f"<b>ID: P1-{row.get('row_id', i+1)}</b>"]
                popup_parts.append(f"<b>Dataset:</b> Prvi niz")
                popup_parts.append(f"<b>Lat:</b> {row['converted_y']:.6f}")
                popup_parts.append(f"<b>Lon:</b> {row['converted_x']:.6f}")
                
                for col in display_columns_1:
                    if col in row and row[col] is not None:
                        popup_parts.append(f"<b>{col}:</b> {row[col]}")
                
                point_data = {
                    'lon': row['converted_x'],
                    'lat': row['converted_y'],
                    'popup': "<br>".join(popup_parts),
                    'color': 'red',
                    'dataset': 'Prvi niz',
                    'point_id': f"P1-{row.get('row_id', i+1)}",
                    'icon': 'circle'
                }
                
                # Dodaj vse atribute za later prikaz
                for col in row:
                    if col not in ['converted_x', 'converted_y', 'geometry']:
                        point_data[f"attr_{col}"] = row[col]
                
                all_points.append(point_data)
    
    # Drugi niz podatkov
    if dataset2_data and x_col_2 and y_col_2 and coord_system_2:
        converted_data_2 = convert_coordinates_from_data(
            dataset2_data, x_col_2, y_col_2, 
            epsgs[coord_system_2]["code"], 4326
        )
        
        for i, row in enumerate(converted_data_2):
            if 'converted_x' in row and 'converted_y' in row:
                # Pripravi popup text
                popup_parts = [f"<b>ID: P2-{row.get('row_id', i+1)}</b>"]
                popup_parts.append(f"<b>Dataset:</b> Drugi niz")
                popup_parts.append(f"<b>Lat:</b> {row['converted_y']:.6f}")
                popup_parts.append(f"<b>Lon:</b> {row['converted_x']:.6f}")
                
                for col in display_columns_2:
                    if col in row and row[col] is not None:
                        popup_parts.append(f"<b>{col}:</b> {row[col]}")
                
                point_data = {
                    'lon': row['converted_x'],
                    'lat': row['converted_y'],
                    'popup': "<br>".join(popup_parts),
                    'color': 'blue',
                    'dataset': 'Drugi niz',
                    'point_id': f"P2-{row.get('row_id', i+1)}",
                    'icon': 'circle'
                }
                
                # Dodaj vse atribute
                for col in row:
                    if col not in ['converted_x', 'converted_y', 'geometry']:
                        point_data[f"attr_{col}"] = row[col]
                
                all_points.append(point_data)
    
    return all_points

# Streamlit UI
st.set_page_config(layout="wide")

st.title("Pretvornik GEO koordinat")

st.markdown("""
### Navodila za uporabo:
1. Prilepite podatke v polje spodaj (prva vrstica naj bodo imena stolpcev)
2. Podatke ločite s tabulatorjem, podpičjem ali presledkom
3. Mapirajte stolpce in določite njihove tipe
4. Po potrebi dodajte še en niz podatkov v drugo polje
""")

# Glavni vnos podatkov

st.subheader("Prvi niz podatkov")
coords_input_1 = st.text_area(
    "Vnesite podatke (prva vrstica = imena stolpcev):",
    height=150,
    placeholder="ID\tGKY\tGKX\tOpis\n1\t448521\t42259\tTočka 1\n2\t448149\t42745\tTočka 2",
    help="Primera vrstica mora vsebovati imena stolpcev",
    key="data1"
)

dataset1_columns = []
dataset1_data = []
column_mapping_1 = {}
coord_system_1 = None
x_col_1 = None
y_col_1 = None
display_columns_1 = []

if coords_input_1:
    headers_1, data_1 = parse_data_with_headers(coords_input_1)
    if headers_1 and data_1:
        dataset1_columns = headers_1
        dataset1_data = data_1
        st.success(f"Prebrano {len(data_1)} vrstic z {len(headers_1)} stolpci")
        
        # Prikaz raw podatkov
        with st.expander("Prebrani podatki"):
            df_preview = pd.DataFrame(data_1)
            st.dataframe(df_preview)
        
        # Mapiranje stolpcev
        st.subheader("Mapiranje stolpcev za prvi niz")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Izbira koordinatnega sistema:**")
            coord_system_1 = st.selectbox(
                "Koordinatni sistem:",
                options=list(epsgs.keys()),
                key="coord_sys_1"
            )
            
            st.write("**Koordinatni stolpci:**")
            x_col_1 = st.selectbox(
                f"Stolpec za {epsgs[coord_system_1]['x_name']}:",
                options=[""] + headers_1,
                key="x_col_1"
            )
            y_col_1 = st.selectbox(
                f"Stolpec za {epsgs[coord_system_1]['y_name']}:",
                options=[""] + headers_1,
                key="y_col_1"
            )
            
        with col2:
            st.write("**Ostali stolpci:**")
            for header in headers_1:
                if header not in [x_col_1, y_col_1]:
                    col_type = st.selectbox(
                        f"Tip stolpca '{header}':",
                        options=["besedilo", "številka", "datum"],
                        key=f"type_{header}_1"
                    )
                    column_mapping_1[header] = col_type

# Drugi vnos podatkov
st.subheader("Drugi niz podatkov (opcijsko)")
coords_input_2 = st.text_area(
    "Vnesite dodatne podatke (prva vrstica = imena stolpcev):",
    height=150,
    placeholder="Ime\tLon\tLat\tKategorija\nLokacija A\t14.3362\t45.5227\tTurizem",
    help="Opcijsko - za prikaz dodatnih točk",
    key="data2"
)

dataset2_columns = []
dataset2_data = []
column_mapping_2 = {}
coord_system_2 = None
x_col_2 = None
y_col_2 = None
display_columns_2 = []

if coords_input_2:
    headers_2, data_2 = parse_data_with_headers(coords_input_2)
    if headers_2 and data_2:
        dataset2_columns = headers_2
        dataset2_data = data_2
        st.success(f"Prebrano {len(data_2)} vrstic z {len(headers_2)} stolpci")
        
        # Prikaz raw podatkov
        with st.expander("Prebrani podatki (drugi niz)"):
            df_preview_2 = pd.DataFrame(data_2)
            st.dataframe(df_preview_2)
        
        # Mapiranje stolpcev
        st.subheader("Mapiranje stolpcev za drugi niz")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Izbira koordinatnega sistema:**")
            coord_system_2 = st.selectbox(
                "Koordinatni sistem:",
                options=list(epsgs.keys()),
                key="coord_sys_2"
            )
            
            st.write("**Koordinatni stolpci:**")
            x_col_2 = st.selectbox(
                f"Stolpec za {epsgs[coord_system_2]['x_name']}:",
                options=[""] + headers_2,
                key="x_col_2"
            )
            y_col_2 = st.selectbox(
                f"Stolpec za {epsgs[coord_system_2]['y_name']}:",
                options=[""] + headers_2,
                key="y_col_2"
            )
            
        with col2:
            st.write("**Ostali stolpci:**")
            for header in headers_2:
                if header not in [x_col_2, y_col_2]:
                    col_type = st.selectbox(
                        f"Tip stolpca '{header}':",
                        options=["besedilo", "številka", "datum"],
                        key=f"type_{header}_2"
                    )
                    column_mapping_2[header] = col_type

# Prikaz na zemljevidu
if (dataset1_data and x_col_1 and y_col_1) or (dataset2_data and x_col_2 and y_col_2):
    st.subheader("Prikaz na zemljevidu")
    
    # Prikaži, kateri nizi podatkov so aktivni
    active_datasets = []
    if dataset1_data and x_col_1 and y_col_1:
        active_datasets.append("Prvi niz")
    if dataset2_data and x_col_2 and y_col_2:
        active_datasets.append("Drugi niz")
    
    if len(active_datasets) == 1:
        st.info(f"📊 Aktivni niz podatkov: {active_datasets[0]}")
    else:
        st.info(f"📊 Aktivna niza podatkov: {' in '.join(active_datasets)}")
    
    # Izbira stolpcev za prikaz - samo za aktivne nize
    display_columns_1 = []
    display_columns_2 = []
    
    cols_for_display = st.columns(len(active_datasets) if len(active_datasets) > 1 else 1)
    
    col_idx = 0
    if dataset1_data and x_col_1 and y_col_1:
        with cols_for_display[col_idx] if len(active_datasets) > 1 else cols_for_display[0]:
            display_columns_1 = st.multiselect(
                "Stolpci za prikaz (prvi niz):",
                options=[col for col in dataset1_columns if col not in [x_col_1, y_col_1]],
                default=[col for col in dataset1_columns if col not in [x_col_1, y_col_1]][:3],
                key="display_cols_1"
            )
        col_idx += 1
    
    if dataset2_data and x_col_2 and y_col_2:
        with cols_for_display[col_idx] if len(active_datasets) > 1 else cols_for_display[0]:
            display_columns_2 = st.multiselect(
                "Stolpci za prikaz (drugi niz):",
                options=[col for col in dataset2_columns if col not in [x_col_2, y_col_2]],
                default=[col for col in dataset2_columns if col not in [x_col_2, y_col_2]][:3],
                key="display_cols_2"
            )
    
    # Pripravi podatke za zemljevid
    if (dataset1_data and x_col_1 and y_col_1) or (dataset2_data and x_col_2 and y_col_2):
        
        if FOLIUM_AVAILABLE:
            # Pripravi podatke za Folium - deluje tudi z enim nizom podatkov
            # Preverimo, če imamo vsaj en popoln niz podatkov
            has_dataset1 = dataset1_data and x_col_1 and y_col_1 and coord_system_1
            has_dataset2 = dataset2_data and x_col_2 and y_col_2 and coord_system_2
            
            if has_dataset1 or has_dataset2:
                # Če nimamo drugega niza, poslji None vrednosti
                if not has_dataset2:
                    dataset2_data, x_col_2, y_col_2, coord_system_2, display_columns_2 = None, None, None, None, []
                if not has_dataset1:
                    dataset1_data, x_col_1, y_col_1, coord_system_1, display_columns_1 = None, None, None, None, []
                
                folium_points = prepare_folium_data(
                    dataset1_data, x_col_1, y_col_1, coord_system_1, display_columns_1,
                    dataset2_data, x_col_2, y_col_2, coord_system_2, display_columns_2
                )
            else:
                # Če nimamo nobenega popolnega niza podatkov
                st.warning("Prosim, nastavite koordinatni sistem in stolpce za vsaj en niz podatkov.")
                folium_points = []
            
            if folium_points:
                # Možnosti prikaza zemljevida
                st.write("**Možnosti prikaza zemljevida:**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    map_style = st.selectbox(
                        "Stil zemljevida:",
                        options=["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter", "Stamen Terrain", "Stamen Toner"],
                        key="map_style"
                    )
                
                with col2:
                    marker_size = st.slider("Velikost označevalcev:", 5, 20, 8, key="marker_size")
                
                with col3:
                    enable_clustering = st.checkbox("Omogoči združevanje točk", value=False, key="enable_clustering")
                
                # Izračunaj center zemljevida
                center_lat = sum(point['lat'] for point in folium_points) / len(folium_points)
                center_lon = sum(point['lon'] for point in folium_points) / len(folium_points)
                
                # Določi zoom level na podlagi razpona koordinat
                lat_range = max(point['lat'] for point in folium_points) - min(point['lat'] for point in folium_points)
                lon_range = max(point['lon'] for point in folium_points) - min(point['lon'] for point in folium_points)
                max_range = max(lat_range, lon_range)
                
                if max_range < 0.01:
                    zoom_level = 14
                elif max_range < 0.1:
                    zoom_level = 12
                elif max_range < 1:
                    zoom_level = 10
                else:
                    zoom_level = 8
                
                # Ustvari Folium zemljevid
                if map_style == "OpenStreetMap":
                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=zoom_level,
                        tiles="OpenStreetMap",
                        font_size='1rem'
                    )
                elif map_style == "CartoDB positron":
                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=zoom_level,
                        tiles="CartoDB positron"
                    )
                elif map_style == "CartoDB dark_matter":
                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=zoom_level,
                        tiles="CartoDB dark_matter"
                    )
                elif map_style == "Stamen Terrain":
                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=zoom_level,
                        tiles=None
                    )
                    folium.TileLayer(
                        tiles="https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png",
                        attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, '
                             'under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. '
                             'Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, '
                             'under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
                        name="Stamen Terrain",
                        overlay=False,
                        control=True
                    ).add_to(m)
                elif map_style == "Stamen Toner":
                    m = folium.Map(
                        location=[center_lat, center_lon],
                        zoom_start=zoom_level,
                        tiles=None
                    )
                    folium.TileLayer(
                        tiles="https://stamen-tiles-{s}.a.ssl.fastly.net/toner/{z}/{x}/{y}.png",
                        attr='Map tiles by <a href="http://stamen.com">Stamen Design</a>, '
                             'under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>. '
                             'Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, '
                             'under <a href="http://www.openstreetmap.org/copyright">ODbL</a>.',
                        name="Stamen Toner",
                        overlay=False,
                        control=True
                    ).add_to(m)
                
                # Dodaj označevalce na zemljevid
                if enable_clustering:
                    try:
                        from folium.plugins import MarkerCluster
                        marker_cluster = MarkerCluster().add_to(m)
                        parent = marker_cluster
                    except ImportError:
                        st.warning("MarkerCluster ni na voljo - prikazujem brez združevanja")
                        parent = m
                else:
                    parent = m
                
                for point in folium_points:
                    folium.CircleMarker(
                        location=[point['lat'], point['lon']],
                        radius=marker_size,
                        popup=folium.Popup(point['popup'], max_width=300),
                        color=point['color'],
                        fill=True,
                        fillColor=point['color'],
                        fillOpacity=0.7,
                        weight=2
                    ).add_to(parent)
                
                # Prikaži zemljevid
                map_data = st_folium(m, width=1100, height=700, returned_objects=["last_object_clicked"])
                
                # Dodaj informacije o interakciji
                st.info("💡 Kliknite na označevalec za prikaz podrobnosti!")
                
                # Prikaži informacije o kliku
                if map_data['last_object_clicked']:
                    clicked_lat = map_data['last_object_clicked']['lat']
                    clicked_lon = map_data['last_object_clicked']['lng']
                    
                    # Najdi najbližjo točko
                    closest_point = None
                    min_distance = float('inf')
                    
                    for point in folium_points:
                        distance = ((point['lat'] - clicked_lat) ** 2 + (point['lon'] - clicked_lon) ** 2) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_point = point
                    
                    if closest_point and min_distance < 0.001:  # Blizu dovolj
                        st.success(f"Kliknili ste na: {closest_point['point_id']} ({closest_point['dataset']})")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Koordinate:**")
                            st.write(f"Lat: {closest_point['lat']:.6f}")
                            st.write(f"Lon: {closest_point['lon']:.6f}")
                        
                        with col2:
                            st.write("**Atributi:**")
                            for key, value in closest_point.items():
                                if key.startswith('attr_') and value is not None:
                                    attr_name = key.replace('attr_', '')
                                    st.write(f"{attr_name}: {value}")
                
                # Legenda - prikaži samo za obstoječe nize
                st.write("**Legenda:**")
                legend_items = []
                if any(point['dataset'] == 'Prvi niz' for point in folium_points):
                    legend_items.append("🔴 Prvi niz podatkov")
                if any(point['dataset'] == 'Drugi niz' for point in folium_points):
                    legend_items.append("🔵 Drugi niz podatkov")
                
                if len(legend_items) == 1:
                    st.markdown(legend_items[0])
                elif len(legend_items) == 2:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(legend_items[0])
                    with col2:
                        st.markdown(legend_items[1])
                
                # Dodatne možnosti za izbiro več točk
                st.subheader("Izbira in filtriranje točk")
                
                # Multiple choice za izbiro točk
                available_points = [f"{point['point_id']} ({point['dataset']})" 
                                  for point in folium_points]
                
                selected_points = st.multiselect(
                    "Izberite točke za podroben prikaz:",
                    options=available_points,
                    key="multi_select_points"
                )
                
                if selected_points:
                    st.write(f"**Podrobnosti za {len(selected_points)} izbrane točke:**")
                    
                    for selected in selected_points:
                        point_id = selected.split(' (')[0]
                        point_data = next((p for p in folium_points if p['point_id'] == point_id), None)
                        
                        if point_data:
                            with st.expander(f"📍 {point_id} - {point_data['dataset']}"):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.write("**Koordinate:**")
                                    st.write(f"Lat: {point_data['lat']:.6f}")
                                    st.write(f"Lon: {point_data['lon']:.6f}")
                                
                                with col2:
                                    st.write("**Atributi:**")
                                    for key, value in point_data.items():
                                        if key.startswith('attr_') and value is not None:
                                            attr_name = key.replace('attr_', '')
                                            st.write(f"{attr_name}: {value}")
                
                # Dodaj možnost izvoza izbranih točk
                if selected_points:
                    selected_data = []
                    for selected in selected_points:
                        point_id = selected.split(' (')[0]
                        point_data = next((p for p in folium_points if p['point_id'] == point_id), None)
                        
                        if point_data:
                            export_row = {
                                'ID': point_id,
                                'Dataset': point_data['dataset'],
                                'Lat': point_data['lat'],
                                'Lon': point_data['lon']
                            }
                            
                            # Dodaj atribute
                            for key, value in point_data.items():
                                if key.startswith('attr_') and value is not None:
                                    attr_name = key.replace('attr_', '')
                                    export_row[attr_name] = value
                            
                            selected_data.append(export_row)
                    
                    if st.button("📥 Prikaži izbrane točke v tabeli"):
                        export_df = pd.DataFrame(selected_data)
                        st.dataframe(export_df, width='stretch')
                        
                        # Možnost download-a
                        csv = export_df.to_csv(index=False)
                        st.download_button(
                            label="⬇️ Prenesi CSV",
                            data=csv,
                            file_name="izbrane_tocke.csv",
                            mime="text/csv"
                        )
            else:
                st.warning("Ni podatkov za prikaz na zemljevidu")
        
        else:
            # Fallback na osnovni st.map če Folium ni na voljo
            st.warning("⚠️ Folium ni na voljo. Uporabljam osnoven zemljevid brez interaktivnih funkcij.")
            
            map_data_list = []
            
            # Prvi niz podatkov
            if dataset1_data and x_col_1 and y_col_1 and coord_system_1:
                converted_data_1 = convert_coordinates_from_data(
                    dataset1_data, x_col_1, y_col_1, 
                    epsgs[coord_system_1]["code"], 4326
                )
                
                for row in converted_data_1:
                    if 'converted_x' in row and 'converted_y' in row:
                        map_data_list.append({
                            'lat': row['converted_y'],
                            'lon': row['converted_x'],
                            'color': [255, 0, 0, 160],
                            'size': 100
                        })
            
            # Drugi niz podatkov
            if dataset2_data and x_col_2 and y_col_2 and coord_system_2:
                converted_data_2 = convert_coordinates_from_data(
                    dataset2_data, x_col_2, y_col_2, 
                    epsgs[coord_system_2]["code"], 4326
                )
                
                for row in converted_data_2:
                    if 'converted_x' in row and 'converted_y' in row:
                        map_data_list.append({
                            'lat': row['converted_y'],
                            'lon': row['converted_x'],
                            'color': [0, 0, 255, 160],
                            'size': 100
                        })
            
            if map_data_list:
                map_df = pd.DataFrame(map_data_list)
                st.map(map_df, zoom=12, size='size', color='color')
                
                # Legenda - prikaži samo za obstoječe nize
                st.write("**Legenda:**")
                legend_items = []
                if dataset1_data and x_col_1 and y_col_1 and coord_system_1:
                    legend_items.append("🔴 Prvi niz podatkov")
                if dataset2_data and x_col_2 and y_col_2 and coord_system_2:
                    legend_items.append("🔵 Drugi niz podatkov")
                
                if len(legend_items) == 1:
                    st.markdown(legend_items[0])
                elif len(legend_items) == 2:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(legend_items[0])
                    with col2:
                        st.markdown(legend_items[1])
            else:
                st.warning("Ni podatkov za prikaz na zemljevidu")
    
    else:
        st.info("Vnesite podatke in označite koordinatne stolpce za začetek dela")
