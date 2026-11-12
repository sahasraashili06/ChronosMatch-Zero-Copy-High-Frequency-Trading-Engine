
import streamlit as st
import subprocess
import sys
from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="ChronosMatch | HFT Engine",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ ChronosMatch")
st.subheader("Zero-Copy High-Frequency Trading Engine")
st.caption("Python Edition | Live Simulation Dashboard")

st.divider()

col1, col2, col3 = st.columns(3)

col1.metric("Verified Tests", "374 / 374")
col2.metric("Code Coverage", "85%")
col3.metric("Previous Throughput", "42,407 ops/sec")

st.divider()

st.subheader("Trading Engine Simulation")

st.write(
    "Execute the actual ChronosMatch Python simulator "
    "and inspect its output."
)

if st.button("▶ Start Simulation", type="primary"):
    with st.spinner("Running ChronosMatch engine..."):
        try:
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                timeout=60
            )

            st.subheader("Execution Status")

            if result.returncode == 0:
                st.success("Simulation completed successfully!")
            else:
                st.error("Simulation encountered an error.")

            output = result.stdout or "No standard output."

            match = re.search(
                r"Rate\s*:\s*~?([\d,]+)\s+orders/sec",
                output
            )

            if match:
                st.metric(
                    "Measured Throughput",
                    match.group(1) + " orders/sec"
                )

            with st.expander("View Actual Simulator Output",
                             expanded=True):
                st.code(output, language="text")

            if result.stderr:
                with st.expander("Error / Warning Details"):
                    st.code(result.stderr)

        except subprocess.TimeoutExpired:
            st.error("Simulation exceeded the 60-second limit.")

        except Exception as error:
            st.error(str(error))

st.divider()

st.subheader("Project Verification")
st.write("Automated testing: 374 tests passed.")
st.write("Previously measured code coverage: 85%.")

st.caption(
    "ChronosMatch | Academic Project Demonstration"
)
