# Fixes Applied to Notebook

## Issues Found
1. **NameError: SCENARIOS not defined** - SCENARIOS was defined inside function, not accessible globally
2. **Empty plots in Jupyter** - `matplotlib.use('Agg')` backend prevents interactive plotting
3. **Missing variable checks** - Plotting cells failed if experiment cell wasn't run first

## Fixes Applied

### 1. SCENARIOS Definition (Cell 834d0e33 - BLOQUE 0)
**Before**: Defined inside `load_scenario_dataset()` function  
**After**: Defined globally in setup cell

```python
SCENARIOS = {
    "sin_pandemia": {...},
    "con_pandemia": {...}
}
```

**Impact**: Test cell (5382dcd7) and all functions can now access SCENARIOS

---

### 2. Remove Matplotlib Backend Lock (Cell 834d0e33)
**Before**: 
```python
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
```

**After**: 
```python
import matplotlib.pyplot as plt  # Let Jupyter manage backend
```

**Impact**: Plots now display inline in Jupyter notebooks + saved to files

---

### 3. Add Safety Checks to Plotting Cells
Applied to cells: **b0ab94f1**, **4d29a121**, **c6fe4883**

**Pattern**:
```python
if 'all_results' not in globals():
    print("ERROR: Execute BLOQUE 5 first (66cbb0f9)")
else:
    # Plot code here
```

**Impact**: Clear error messages instead of cryptic NameError

---

## Execution Order

### For Full Analysis (601 assets, ~8 minutes):
1. Cell 834d0e33 - Setup
2. Cell d4d09054 - Load script
3. Cell 20ad7ea0 - Parameters
4. Cell e41801a3 - Functions
5. Cell 5382dcd7 - Tests (validates everything works)
6. **Cell 66cbb0f9 - Main Experiment** (h7_f2, 601 assets)
7. **Cell c45e3529 - Export CSVs**
8. **Cell 8b12dac9 - Create Comparison**
9. Cell b0ab94f1 - Plot 1-2 (bar charts)
10. Cell 4d29a121 - Plot 3 (scatter plots)
11. Cell c6fe4883 - Plot 4-5 (heatmaps)

### For Quick Test (10 assets, ~1 minute):
Run cells 834d0e33 → d4d09054 → 20ad7ea0 → e41801a3 → 5382dcd7

This validates the pipeline without running the full analysis.

---

## What's Fixed

| Issue | Location | Status |
|-------|----------|--------|
| SCENARIOS undefined | Global scope | ✓ FIXED |
| Matplotlib backend | Setup cell | ✓ FIXED |
| Empty plots | Removed 'Agg' backend | ✓ FIXED |
| NameError in tests | SCENARIOS now global | ✓ FIXED |
| NameError in plots | Added safety checks | ✓ FIXED |
| Missing seaborn | Used matplotlib.imshow() | ✓ FIXED (prev. session) |

---

## How to Use the Notebook

### Option 1: Run Full Analysis
```
Execute cells in order from top to bottom
Takes ~8 minutes for 601 assets
Generates all 5 visualizations
```

### Option 2: Quick Validation
```
Execute only: 834d0e33 → d4d09054 → 20ad7ea0 → e41801a3 → 5382dcd7
Takes ~30 seconds
Validates all functions work
Shows shape of data (2717 and 3473 rows)
```

### Option 3: Disable Logs
In cell 834d0e33, change:
```python
DEBUG = True   # Before
DEBUG = False  # After
```

---

## Expected Output

After running full analysis, you should see:
- ✓ CSVs generated in outputs folder
- ✓ 4 bar/scatter plot figures display inline
- ✓ 2 heatmap figures display inline
- ✓ Console output showing Sharpe comparison table

**If plots are empty**: Make sure you executed cell 66cbb0f9 (experiment) first

---

## Files Modified This Session
- `markowitz_cvxpy_benchmark_teorico_rebalanceo_pandemia.ipynb` (5 cells)
- `run_analysis.py` (UTF-8 encoding fix)

---

All errors should now be resolved. The notebook is ready for full execution.
