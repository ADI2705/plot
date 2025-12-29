import pandas as pd
import plotly.express as px
import plotly.io as pio
import os
import numpy as np

# Set input file
INPUT_FILE = 'fio_Sheet.csv'
# Set input file
OUTPUT_DIR = "/home/user/plot/JBOF_RDMA"

# Define test types to generate reports for
TEST_TYPES = ['write', 'read', 'randwrite', 'randread', 'randrw']

# Metrics mapping
METRICS = {
    'bw': 'Bandwidth (MiB/s)',
    'iops': 'IOPS',
    'lat': 'Latency (µs)'
}

def parse_bw(s):
    if pd.isna(s):
        return np.nan
    s = str(s).replace('MiB/s', '').strip()
    return float(s)

def parse_iops(s):
    if pd.isna(s):
        return np.nan
    s = str(s).strip()
    if 'k' in s:
        return float(s.replace('k', '')) * 1000
    else:
        return float(s)

def parse_lat(s):
    if pd.isna(s):
        return np.nan
    s = str(s).replace(' µs', '').strip()
    return float(s)

def load_and_prep_data(filepath):
    print(f"Loading data from {filepath}...")
    df = pd.read_csv(filepath)
    
    # Forward fill missing values (CSV uses implied values for block_size and iodepth)
    df.ffill(inplace=True)
    
    # Standardize column name
    df.rename(columns={'block size': 'block_size'}, inplace=True)
    
    # Standardize block size values to ensure clean grouping
    df['block_size'] = df['block_size'].str.upper() # 4k -> 4K
    
    # Drop rows with NaN iodepth or numjobs if any remain
    df = df.dropna(subset=['iodepth', 'numjobs'])
    
    # Ensure they are integers
    df['iodepth'] = df['iodepth'].astype(int)
    df['numjobs'] = df['numjobs'].astype(int)
    
    # Create Composite X-Axis Column
    df['iodepth_numjobs'] = df['iodepth'].astype(str) + '_' + df['numjobs'].astype(str)
    
    return df

def get_sorted_x_order(df):
    # Sort order logic: 1_1, 1_2, ... based on numerical values of iodepth and numjobs
    unique_vals = df[['iodepth', 'numjobs', 'iodepth_numjobs']].drop_duplicates()
    unique_vals = unique_vals.sort_values(by=['iodepth', 'numjobs'])
    return unique_vals['iodepth_numjobs'].tolist()

def generate_html_report(test_type, df, x_order):
    print(f"Generating report for {test_type}...")
    
    # Filter columns relevant to this test type
    # Columns in CSV are like: write_bw, write_iops, write_lat
    cols = {
        'bw': f'{test_type}_bw',
        'iops': f'{test_type}_iops',
        'lat': f'{test_type}_lat'
    }
    
    # Filter data for non-empty values in these columns
    # We take all rows, but we need to parse the values first
    report_df = df.copy()
    
    # Parse columns
    report_df['params_bw'] = report_df[cols['bw']].apply(parse_bw)
    report_df['params_iops'] = report_df[cols['iops']].apply(parse_iops)
    report_df['params_lat'] = report_df[cols['lat']].apply(parse_lat)
    
    # Sort for graphing (ensure lines are connected correctly in order of x-axis)
    # We first map iodepth_numjobs to an integer rank for sorting
    x_rank_map = {val: i for i, val in enumerate(x_order)}
    report_df['x_rank'] = report_df['iodepth_numjobs'].map(x_rank_map)
    
    # Also sort by block size so the legend is consistent
    # Map 4K->1, 128K->2, 1M->3
    bs_map = {'4K': 1, '128K': 2, '512K': 3, '1M': 4} # Add more if needed
    report_df['bs_rank'] = report_df['block_size'].map(lambda x: bs_map.get(x, 99))
    
    report_df.sort_values(by=['bs_rank', 'x_rank'], inplace=True)
    
    # Generate Graphs
    figs = {}
    
    # 1. Bandwidth
    figs['bw'] = px.line(
        report_df, 
        x='iodepth_numjobs', 
        y='params_bw', 
        color='block_size',
        title=None,
        labels={'iodepth_numjobs': 'IO Depth_Num Jobs', 'params_bw': 'Bandwidth (MiB/s)', 'block_size': 'Block Size'},
        markers=True,
        category_orders={'iodepth_numjobs': x_order}
    )
    
    # 2. IOPS
    figs['iops'] = px.line(
        report_df, 
        x='iodepth_numjobs', 
        y='params_iops', 
        color='block_size',
        title=None,
        labels={'iodepth_numjobs': 'IO Depth_Num Jobs', 'params_iops': 'IOPS', 'block_size': 'Block Size'},
        markers=True,
        category_orders={'iodepth_numjobs': x_order}
    )

    # 3. Latency
    figs['lat'] = px.line(
        report_df, 
        x='iodepth_numjobs', 
        y='params_lat', 
        color='block_size',
        title=None,
        labels={'iodepth_numjobs': 'IO Depth_Num Jobs', 'params_lat': 'Latency (µs)', 'block_size': 'Block Size'},
        markers=True,
        category_orders={'iodepth_numjobs': x_order}
    )

    # Convert figures to HTML divs
    graph_htmls = {}
    for key, fig in figs.items():
        # Update styling to match dark theme preference if needed, though px.line defaults are usually white background
        # The user's sample has white graphs on dark background? No, looks like standard plotly.
        # But let's check the sample style again.
        # "body { background: #111; color: white !important; }"
        # We should make the graph background transparent or dark?
        # Sample had white paper_bgcolor? Let's assume standard template but just ensuring it looks good in the container.
        # Actually standard plotly has white background.
        
        graph_htmls[key] = pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

    # Sort helpers
    def sort_key_block_size(val):
        val = str(val).upper()
        if 'K' in val: return float(val.replace('K', '')) * 1024
        if 'M' in val: return float(val.replace('M', '')) * 1024 * 1024
        try: return float(val)
        except: return 0

    def sort_key_int(val):
        try: return int(val)
        except: return 0

    block_sizes = sorted([str(x) for x in df['block_size'].unique() if pd.notna(x)], key=sort_key_block_size)
    num_jobs = sorted([str(x) for x in df['numjobs'].unique() if pd.notna(x)], key=sort_key_int)
    io_depths = sorted([str(x) for x in df['iodepth'].unique() if pd.notna(x)], key=sort_key_int)

    # Construct HTML
    html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>FIO Benchmark Dashboard</title>
                <style>
  body {{
    background: #111;
    color: white !important;
  }}
</style>

        </head>
        <body>
            <h1>FIO Benchmark Dashboard </h1>
                <h1>{test_type.capitalize()}</h1>
            <p>Test Type: {test_type} | Block Sizes: {', '.join(block_sizes)} | Num Jobs: {', '.join(num_jobs)} | IO Depth: {', '.join(io_depths)}</p>
            
            <h2>1. Bandwidth (MiB/s)</h2>
            <div>{graph_htmls['bw']}</div>
            
            <h2>2. IOPS</h2>
            <div>{graph_htmls['iops']}</div>
            
            <h2>3. Latency (µs)</h2>
            <div>{graph_htmls['lat']}</div>
        </body>
        </html>
    """
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = os.path.join(OUTPUT_DIR, f"{test_type}.html")

    with open(filename, 'w') as f:
        f.write(html_content)
    print(f"Saved {filename}")

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    df = load_and_prep_data(INPUT_FILE)
    x_order = get_sorted_x_order(df)
    
    for test in TEST_TYPES:
        generate_html_report(test, df, x_order)

if __name__ == "__main__":
    main()
