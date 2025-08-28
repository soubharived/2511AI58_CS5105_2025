import streamlit as st
import pandas as pd
from io import BytesIO
import re
from collections import deque
import math
import zipfile

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="Student Grouping Dashboard",
    layout="centered"
)

st.title("Student Grouping Dashboard")
st.markdown("Easily divide students into multiple groups and view insightful branch distribution statistics.")

DEFAULT_PARTS = 12
priority_branches = ["AI","CB","CE","CH","CS","CT","EC","MC","MM","MT"]  

# ---------- HELPERS ----------
def branch_finder(roll_id: str) -> str:
    if pd.isna(roll_id):
        return "NA"
    res = re.search(r"[A-Z]{2}", str(roll_id))
    return res.group(0) if res else "NA"

def compile_summary(bundles, total_parts):
    codes = sorted(set().union(*[set(pd.DataFrame(b)["Branch"]) for b in bundles if b]))
    summary = pd.DataFrame(0, index=[f"Group {i+1}" for i in range(total_parts)], columns=codes + ["Total"])
    
    for idx, pack in enumerate(bundles, start=1):
        pack_df = pd.DataFrame(pack)
        if not pack_df.empty:
            for code in codes:
                summary.loc[f"Group {idx}", code] = int((pack_df["Branch"] == code).sum())
            summary.loc[f"Group {idx}", "Total"] = int(len(pack_df))
    return summary.reset_index().rename(columns={"index": "Group"})


# ---------- ALGORITHMS ----------
def branchwise_allocation(records, total_parts):
    active_codes = list(pd.unique(records["Branch"]))
    cycle = [c for c in priority_branches if c in active_codes] + [c for c in active_codes if c not in priority_branches]

    stock = {c: deque([row for _, row in records[records["Branch"] == c].iterrows()]) for c in cycle}
    size = len(records)
    base_size = size // total_parts
    remainder = size % total_parts
    targets = [base_size + (1 if i < remainder else 0) for i in range(total_parts)]

    bundles = [[] for _ in range(total_parts)]
    for gi in range(total_parts):
        limit = targets[gi]
        while len(bundles[gi]) < limit:
            moved = False
            for c in cycle:
                if len(bundles[gi]) >= limit:
                    break
                if stock[c]:
                    bundles[gi].append(stock[c].popleft())
                    moved = True
            if not moved:
                break
    return bundles

def uniform_allocation(records, total_parts):
    size = len(records)
    pack_size = math.ceil(size / total_parts)
    bundles, leftovers = [], []

    freq = records["Branch"].value_counts()
    sorted_codes = list(freq.sort_values(ascending=False).index)
    partitions = {c: [r for _, r in records[records["Branch"] == c].iterrows()] for c in sorted_codes}

    for c in sorted_codes:
        rows, k = partitions[c], 0
        while len(rows) - k >= pack_size:
            bundles.append(rows[k:k+pack_size])
            k += pack_size
        if k < len(rows):
            leftovers.append(rows[k:])
    leftovers = deque(sorted(leftovers, key=lambda blk: -len(blk)))

    while leftovers:
        block = leftovers.popleft()
        group = list(block)
        remain_space = pack_size - len(group)
        while remain_space > 0 and leftovers:
            candidate = leftovers.popleft()
            if len(candidate) <= remain_space:
                group.extend(candidate)
                remain_space -= len(candidate)
            else:
                take, left = candidate[:remain_space], candidate[remain_space:]
                group.extend(take)
                leftovers.appendleft(left)
                remain_space = 0
        bundles.append(group)

    while len(bundles) < total_parts:
        bundles.append([])
    return bundles


# ---------- MAIN APP ----------
def main():
    st.sidebar.header(" Configuration")
    excel_file = st.sidebar.file_uploader("Upload Excel File", type=["xlsx"])
    total_parts = st.sidebar.slider("Select Number of Groups", 2, 50, DEFAULT_PARTS)

    if excel_file:
        try:
            records = pd.read_excel(excel_file)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            return

        for field in ["Roll","Name","Email"]:
            if field not in records.columns:
                records[field] = ""
        records["Branch"] = records["Roll"].apply(branch_finder)

        branchwise = branchwise_allocation(records, total_parts)
        stats_branchwise = compile_summary(branchwise, total_parts)
        uniform = uniform_allocation(records, total_parts)
        stats_uniform = compile_summary(uniform, total_parts)

        st.success(" File processed successfully!")

        

        # Tabs for strategies
        tab1, tab2 = st.tabs([" Branch-wise Method", "Uniform Method"])
        with tab1:
            st.dataframe(stats_branchwise, use_container_width=True, hide_index=True)
            with st.expander("Explore Branch-wise Groups"):
                for gi, pack in enumerate(branchwise, start=1):
                    st.markdown(f"**Group {gi}**")
                    pack_df = pd.DataFrame(pack)
                    st.dataframe(pack_df[["Roll","Name","Email","Branch"]], hide_index=True)

        with tab2:
            st.dataframe(stats_uniform, use_container_width=True, hide_index=True)
            with st.expander(" Explore Uniform Groups"):
                for gi, pack in enumerate(uniform, start=1):
                    st.markdown(f"**Group {gi}**")
                    pack_df = pd.DataFrame(pack)
                    st.dataframe(pack_df[["Roll","Name","Email","Branch"]], hide_index=True)

        # ---------- Generate Downloadable Reports ----------
        output_excel = BytesIO()
        with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
            stats_branchwise.to_excel(writer, sheet_name="Branchwise_Summary", index=False)
            stats_uniform.to_excel(writer, sheet_name="Uniform_Summary", index=False)

            for gi, pack in enumerate(branchwise, start=1):
                pd.DataFrame(pack).to_excel(writer, sheet_name=f"Branchwise_{gi}", index=False)
            for gi, pack in enumerate(uniform, start=1):
                pd.DataFrame(pack).to_excel(writer, sheet_name=f"Uniform_{gi}", index=False)

        output_excel.seek(0)
        st.download_button(
            "⬇ Download Group Report (Excel)",
            data=output_excel,
            file_name="student_groups.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ---------- NEW FEATURE: CSV files of each branch ----------
        csv_zip = BytesIO()
        with zipfile.ZipFile(csv_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for branch_code, df_branch in records.groupby("Branch"):
                csv_bytes = df_branch.to_csv(index=False).encode("utf-8")
                zipf.writestr(f"{branch_code}_students.csv", csv_bytes)

        csv_zip.seek(0)
        st.download_button(
            "Download Branch-wise CSVs (ZIP)",
            data=csv_zip,
            file_name="branches_csv.zip",
            mime="application/zip",
        )


main()
