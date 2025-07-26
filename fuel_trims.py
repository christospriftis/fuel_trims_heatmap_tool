import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ----------------------------
# PAGE SETUP
# ----------------------------
st.set_page_config(page_title="Fuel Trim Heatmap Tool", layout="wide")
st.title("📊 Fuel Trim Heatmap Generator")

# ----------------------------
# SIDEBAR CONFIGURATION
# ----------------------------
st.sidebar.header("⚙️ Configuration")
rpm_bin_size = st.sidebar.selectbox("RPM Bin Size", options=[250, 500, 1000], index=1)
map_bin_size = st.sidebar.selectbox("MAP Bin Size (mbar)", options=[25, 50, 100], index=1)
min_samples = st.sidebar.slider("Minimum Samples per Cell", min_value=1, max_value=50, value=1)
trim_range = st.sidebar.slider("Fuel Trim Range (%)", min_value=-50, max_value=50, value=(-50, 50))
update_button = st.sidebar.button("🔁 Update Heatmaps")

REQUIRED_COLUMNS = ['MAP_mbar', 'RPM', 'STFT', 'LTFT']

# ----------------------------
# STEP 1: LOG FILE UPLOAD
# ----------------------------
st.markdown("### Step 1: Upload the **Log Data CSV**")
log_file = st.file_uploader("Upload Log File", type="csv", key="log")

if log_file is not None:
    st.success("✅ Log file uploaded successfully.")

    # ----------------------------
    # STEP 2: MAPPING FILE UPLOAD
    # ----------------------------
    st.markdown("### Step 2: Upload the **Column Mapping CSV**")
    map_file = st.file_uploader("Upload Mapping File", type="csv", key="mapping")

    if map_file is not None:
        st.success("✅ Mapping file uploaded successfully.")

        try:
            # LOAD DATA
            df_log = pd.read_csv(log_file)
            df_map = pd.read_csv(map_file)

            if 'original' not in df_map.columns or 'new' not in df_map.columns:
                st.error("❌ Mapping file must contain 'original' and 'new' columns.")
                st.stop()

            column_mapping = dict(zip(df_map['original'], df_map['new']))
            missing = [col for col in REQUIRED_COLUMNS if col not in column_mapping.values()]
            if missing:
                st.error(f"❌ Mapping file is missing required columns: {missing}")
                st.stop()

            df_log.rename(columns=column_mapping, inplace=True)
            df = df_log.dropna(subset=REQUIRED_COLUMNS)
            df = df[(df['MAP_mbar'] > 0) & (df['RPM'] > 0)]

            df['RPM_bin'] = (df['RPM'] // rpm_bin_size) * rpm_bin_size
            df['MAP_bin'] = (df['MAP_mbar'] // map_bin_size) * map_bin_size
            df['TotalTrim'] = df['STFT'] + df['LTFT']

            trim_modes = {
                "Short Term Fuel Trim (STFT)": 'STFT',
                "Long Term Fuel Trim (LTFT)": 'LTFT',
                "Combined Fuel Trim (STFT + LTFT)": 'TotalTrim',
                "STFT & LTFT Side-by-Side": None
            }

            selected_mode = st.selectbox("Select Heatmap View", list(trim_modes.keys()))

            def create_trim_heatmap(pivot_df, count_df, title, colorscale, colorbar_title):
                min_trim, max_trim = trim_range
                mask = (count_df >= min_samples) & (pivot_df >= min_trim) & (pivot_df <= max_trim)
                z = pivot_df.where(mask)
                text = [[f"{val:.1f}" if pd.notna(val) else "" for val in row] for row in z.values]

                fig = go.Figure(go.Heatmap(
                    z=z.values,
                    x=z.columns,
                    y=z.index,
                    text=text,
                    texttemplate="%{text}",
                    colorscale=colorscale,
                    colorbar=dict(title=colorbar_title),
                    hoverinfo="x+y+z"
                ))
                fig.update_layout(title=title, xaxis_title="RPM", yaxis_title="MAP (mbar)")
                # Y-axis not reversed here, so higher MAP values appear higher
                return fig, mask

            def create_count_heatmap(count_df, mask, title):
                z = count_df.where(mask)
                text = [[f"{int(val)}" if pd.notna(val) else "" for val in row] for row in z.values]

                fig = go.Figure(go.Heatmap(
                    z=z.values,
                    x=z.columns,
                    y=z.index,
                    text=text,
                    texttemplate="%{text}",
                    colorscale='Blues',
                    colorbar=dict(title="Samples"),
                    hoverinfo="x+y+z"
                ))
                fig.update_layout(title=title, xaxis_title="RPM", yaxis_title="MAP (mbar)")
                # Y-axis normal here too
                return fig

            def create_timeseries_chart(df):
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    y=df['STFT'], mode='lines', name='STFT', line=dict(color='blue')))
                fig.add_trace(go.Scatter(
                    y=df['LTFT'], mode='lines', name='LTFT', line=dict(color='green')))
                fig.add_trace(go.Scatter(
                    y=df['TotalTrim'], mode='lines', name='STFT + LTFT', line=dict(color='red')))

                fig.update_layout(
                    title="📈 Fuel Trim Time Series",
                    xaxis_title="Sample Index",
                    yaxis_title="Fuel Trim (%)",
                    hovermode="x unified",
                    xaxis=dict(showspikes=True, spikemode='across', spikesnap='cursor', showline=True),
                    yaxis=dict(showspikes=True, spikemode='across', spikesnap='cursor', showline=True),
                )
                return fig

            if update_button:
                if selected_mode != "STFT & LTFT Side-by-Side":
                    value_col = trim_modes[selected_mode]
                    pivot = df.pivot_table(index='MAP_bin', columns='RPM_bin', values=value_col, aggfunc='mean')
                    count = df.pivot_table(index='MAP_bin', columns='RPM_bin', values=value_col, aggfunc='count')

                    fig_trim, valid_mask = create_trim_heatmap(pivot, count, selected_mode, 'Viridis', "Trim (%)")
                    fig_count = create_count_heatmap(count, valid_mask, "Sample Counts")

                    col1, col2 = st.columns(2)
                    col1.plotly_chart(fig_trim, use_container_width=True)
                    col2.plotly_chart(fig_count, use_container_width=True)

                else:
                    pivot_stft = df.pivot_table(index='MAP_bin', columns='RPM_bin', values='STFT', aggfunc='mean')
                    pivot_ltft = df.pivot_table(index='MAP_bin', columns='RPM_bin', values='LTFT', aggfunc='mean')
                    count = df.pivot_table(index='MAP_bin', columns='RPM_bin', values='STFT', aggfunc='count')

                    fig_stft, mask_stft = create_trim_heatmap(pivot_stft, count, "Short Term Fuel Trim (STFT)", 'Viridis', "STFT (%)")
                    fig_ltft, mask_ltft = create_trim_heatmap(pivot_ltft, count, "Long Term Fuel Trim (LTFT)", 'Plasma', "LTFT (%)")
                    combined_mask = mask_stft | mask_ltft
                    fig_count = create_count_heatmap(count, combined_mask, "Sample Counts")

                    col1, col2 = st.columns(2)
                    col1.plotly_chart(fig_stft, use_container_width=True)
                    col2.plotly_chart(fig_ltft, use_container_width=True)
                    st.plotly_chart(fig_count, use_container_width=True)

                # 📈 TIME SERIES CHART
                st.markdown("---")
                st.markdown("### 📉 Fuel Trim Time Series")
                ts_chart = create_timeseries_chart(df)
                st.plotly_chart(ts_chart, use_container_width=True)

            else:
                st.info("⬅️ Adjust options in the sidebar and click '🔁 Update Heatmaps' to refresh visualizations.")

        except Exception as e:
            st.error(f"❌ An error occurred: {e}")
