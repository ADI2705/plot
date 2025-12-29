import os
import pandas as pd
import plotly.express as px
import plotly.io as pio
import re

def get_sort_key(folder_name):
    """
    Sort key for folders.
    Priority:
    1. Parse block size (4k, 128k, 1M) -> convert to bytes for value comparison.
    2. Test type (alphabetical).
    3. Other folders (e.g., 'precondition') go to the end.
    """
    # Regex to parse '4k_write', '1M_randread', etc.
    match = re.match(r'(\d+)([kKmMgG])_([a-zA-Z]+)', folder_name)
    if match:
        size_val = int(match.group(1))
        unit = match.group(2).lower()
        suffix = match.group(3)
        
        multiplier = 1
        if unit == 'k': multiplier = 1024
        elif unit == 'm': multiplier = 1024**2
        elif unit == 'g': multiplier = 1024**3
        
        bytes_val = size_val * multiplier
        return (0, bytes_val, suffix)
    
    # Special handling for 'precondition' or others to be at the end
    return (1, folder_name)

# Define input directory
MONITORING_DIR = 'monitoring'

# Define output files
OUTPUT_FILES = {
    'cpu': 'cpu_graphs.html',
    'memory': 'memory_graph.html',
    'network': 'network_graphs.html'
}

def load_data(folder_path, file_type):
    """
    Load CSV data from a specific folder and file type.
    Handles case-insensitive 'Timestamp' column.
    """
    csv_path = os.path.join(folder_path, f"{file_type}.csv")
    if not os.path.exists(csv_path):
        return None
    
    try:
        # on_bad_lines='skip' ensures we don't crash on malformed rows (e.g. extra commas)
        df = pd.read_csv(csv_path, on_bad_lines='skip')
        # Normalize timestamp column name
        if 'Timestamp' in df.columns:
            df.rename(columns={'Timestamp': 'timestamp'}, inplace=True)
        
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df.dropna(subset=['timestamp'], inplace=True)
            return df
        else:
            print(f"Warning: No 'timestamp' column in {csv_path}")
            return None
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")
        return None

def generate_cpu_section(folder_name, df):
    """
    Generate HTML section for CPU graphs.
    """
    if df is None or df.empty:
        return ""
    
    # Check for expected columns
    required_cols = ['user%', 'system%', 'idle%']
    if not all(col in df.columns for col in required_cols):
        return f"<div><p>Missing columns in {folder_name}/cpu.csv</p></div>"

    fig = px.line(
        df,
        x='timestamp',
        y=['user%', 'system%', 'idle%'],
        title=f"{folder_name} - CPU Usage",
        labels={'value': 'Percentage', 'variable': 'Metric'},
        color_discrete_map={
            'user%': '#FF6B6B',      # Red
            'system%': '#4ECDC4',    # Teal
            'idle%': '#45B7D1'       # Blue
        }
    )
    fig.update_layout(hovermode="closest")
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)

def generate_memory_section(folder_name, df):
    """
    Generate HTML section for Memory graphs.
    """
    if df is None or df.empty:
        return ""

    # Expected columns: Used_Memory_MB, Free_Memory_MB, Buffer_Cache_MB, Available_Memory_MB
    plot_cols = ['Used_Memory_MB', 'Free_Memory_MB', 'Buffer_Cache_MB', 'Available_Memory_MB']
    available_cols = [c for c in plot_cols if c in df.columns]
    
    if not available_cols:
        return f"<div><p>Missing memory columns in {folder_name}/memory.csv</p></div>"

    fig = px.line(
        df,
        x='timestamp',
        y=available_cols,
        title=f"{folder_name} - Memory Usage (MB)",
        labels={'value': 'MB', 'variable': 'Metric'},
        color_discrete_map={
            'Used_Memory_MB': '#E74C3C',        # Red
            'Free_Memory_MB': '#27AE60',        # Green
            'Buffer_Cache_MB': '#F39C12',       # Orange
            'Available_Memory_MB': '#3498DB'    # Blue
        }
    )
    fig.update_layout(hovermode="closest")
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)

def generate_network_sections(folder_name, df):
    """
    Generate a SINGLE HTML section for Network graphs (all interfaces combined).
    """
    if df is None or df.empty:
        return []

    # Identify all RX/TX columns
    # Example cols: eno1_RX_MBps, eno1_TX_MBps, eno2_RX_MBps, ...
    plot_cols = [c for c in df.columns if c.endswith('_RX_MBps') or c.endswith('_TX_MBps')]
    
    if not plot_cols:
        return []

    fig = px.line(
        df,
        x='timestamp',
        y=plot_cols,
        title=f"{folder_name} - Network Throughput (All Interfaces)",
        labels={'value': 'MBps', 'variable': 'Metric'}
    )
    fig.update_layout(hovermode="closest")
    
    # Return list containing single plot (to match structure)
    return [pio.to_html(fig, full_html=False, include_plotlyjs=False)]

def create_html_file(filename, title, sections):
    """
    Write gathered sections to a single HTML file.
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                background-color: #f5f5f5;
            }}
            .graph-container {{
                background-color: white;
                margin-bottom: 20px;
                padding: 10px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{ text-align: center; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        {''.join([f'<div class="graph-container">{s}</div>' for s in sections])}
    </body>
    </html>
    """
    
    with open(filename, 'w') as f:
        f.write(html_content)
    print(f"Saved {filename}")

def main():
    if not os.path.exists(MONITORING_DIR):
        print(f"Error: Directory '{MONITORING_DIR}' not found.")
        return

    # Get all subdirectories in monitoring folder
    test_folders = [f for f in os.listdir(MONITORING_DIR) if os.path.isdir(os.path.join(MONITORING_DIR, f))]
    
    # Sort them nicely (e.g. by block size then type)
    test_folders.sort(key=get_sort_key)

    cpu_sections = []
    memory_sections = []
    network_sections = []

    for folder_name in test_folders:
        folder_path = os.path.join(MONITORING_DIR, folder_name)
        print(f"Processing {folder_name}...")

        # --- CPU ---
        cpu_df = load_data(folder_path, 'cpu')
        cpu_html = generate_cpu_section(folder_name, cpu_df)
        if cpu_html:
            cpu_sections.append(cpu_html)

        # --- Memory ---
        mem_df = load_data(folder_path, 'memory')
        mem_html = generate_memory_section(folder_name, mem_df)
        if mem_html:
            memory_sections.append(mem_html)

        # --- Network ---
        net_df = load_data(folder_path, 'network')
        net_htmls = generate_network_sections(folder_name, net_df)
        network_sections.extend(net_htmls)

    # Write Output Files
    create_html_file(OUTPUT_FILES['cpu'], "CPU Usage Reports", cpu_sections)
    create_html_file(OUTPUT_FILES['memory'], "Memory Usage Reports", memory_sections)
    create_html_file(OUTPUT_FILES['network'], "Network Throughput Reports", network_sections)

if __name__ == "__main__":
    main()
