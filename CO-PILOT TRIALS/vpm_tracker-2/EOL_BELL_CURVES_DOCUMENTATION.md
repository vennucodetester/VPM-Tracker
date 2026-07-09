# EOL Bell Curves Analysis Workbook — Complete Documentation

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Part 1: Foundational Concepts](#part-1-foundational-concepts)
3. [Part 2: Problem Statement](#part-2-problem-statement)
4. [Part 3: Solution Architecture](#part-3-solution-architecture)
5. [Part 4: Step-by-Step Implementation](#part-4-step-by-step-implementation)
6. [Part 5: Formula Details](#part-5-formula-details)
7. [Part 6: Function Compatibility](#part-6-function-compatibility)
8. [Part 7: Usage Instructions](#part-7-usage-instructions)

---

## Executive Summary

The EOL Bell Curves workbook is a formula-driven Excel analysis tool that processes end-of-line test data for two types of condensing units (LT and MT). It visualizes the distribution of 12 key measurements (temperatures, voltages, currents) as bell curves, identifies statistical outliers, and recommends tolerance bands using three different methods.

**Core Philosophy:** Every calculated number is traceable to source data via Excel formulas. Users can click any cell and see exactly how its value was computed.

**Key Deliverables:**
- Bell curve charts showing normal distribution overlay
- Statistical summaries (mean, standard deviation, min, max)
- Outlier identification using z-score method
- Three tolerance band methods (3-sigma, percentile-based, IQR-based)
- Full formula traceability from output back to raw data

---

## Part 1: Foundational Concepts

### 1.1 The Normal Distribution and Bell Curves

A **bell curve** (or normal distribution) is a probability distribution that describes how values in a dataset are spread around a central value. Most real-world measurements follow this pattern.

**Key characteristics:**
- **Symmetrical:** The left and right sides are mirror images
- **Peak at center:** The highest point represents the mean (average)
- **Tails:** Values far from the mean are increasingly rare
- **68-95-99.7 Rule:** 
  - ~68% of data falls within 1 standard deviation (σ) of the mean (μ)
  - ~95% falls within 2σ
  - ~99.7% falls within 3σ

### 1.2 Standard Deviation (σ)

Standard deviation measures how spread out data is from the average.

- **Small σ:** Data points cluster tightly around the mean (narrow bell curve)
- **Large σ:** Data points are scattered widely (wide, flat bell curve)

**Formula concept:** σ = √(average of squared differences from mean)

### 1.3 Z-Score

A **z-score** tells us how many standard deviations a single value is from the mean.

**Formula:** Z = (Value − Mean) / StdDev

**Interpretation:**
- Z = 0: Value equals the mean
- Z = +2: Value is 2 standard deviations above the mean
- Z = −3: Value is 3 standard deviations below the mean
- |Z| > 3: Value is considered a statistical outlier (extremely rare)

### 1.4 Outliers

An **outlier** is a data point that is unusually far from the mean—far enough that it suggests either:
1. A measurement error
2. A rare but genuine event
3. A process anomaly that needs investigation

**Detection methods:**
- **3-sigma rule:** |Z| > 3 (approximately 1 in 740 chance if normal distribution)
- **Percentile rule:** Below 1st percentile or above 99th percentile
- **IQR rule:** Beyond 1.5 × interquartile range from Q1 or Q3

### 1.5 Pass vs. All Data

When analyzing test data with mixed pass/fail results:

- **All Data:** Includes both passing and failing units
- **Pass-Only Data:** Includes only units that passed the overall test

**Why this matters:** Failing units may have abnormal measurements that skew statistics. By computing pass-only statistics separately, we see what "normal" looks like for passing units, which is better for tolerance band recommendations.

### 1.6 Tolerance Bands

A **tolerance band** is a range (low, high) that defines acceptable values.

**Three methods compared:**
1. **3-Sigma Method:** Mean ± 3σ (captures ~99.7% of normal data)
2. **Percentile Method:** 1st to 99th percentile (empirical, captures 98% of observed data)
3. **IQR Method:** Q1 − 1.5×IQR to Q3 + 1.5×IQR (Tukey fences, conservative)

### 1.7 Histogram and Binning

A **histogram** groups data into equal-width ranges (bins) and counts how many values fall in each bin.

**Why histograms are useful:**
- Visual representation of data distribution
- Easy to see if data is roughly bell-shaped
- Can overlay a theoretical bell curve to see fit quality
- Identifies multimodal distributions (multiple peaks)

**Bin calculation:**
- **Bin width:** (Max − Min + StdDev) / 30 (30 bins is a good default for 940 records)
- **Bin start:** Min − 0.5 × StdDev (extends slightly below minimum)
- **Bin center:** Used for plotting the histogram

---

## Part 2: Problem Statement

### 2.1 The Business Need

**Context:** Two types of condensing units (LT and MT) undergo end-of-line (EOL) testing to verify they meet performance specifications. Each unit is tested and marked as Pass or Fail.

**Questions to answer:**
1. What do the distributions of key measurements look like?
2. Which units have abnormal measurements (outliers)?
3. What measurement ranges should be considered acceptable (tolerance bands)?
4. Are there differences between LT and MT units?

### 2.2 The Data

**Source file:** Run test data start to 4-27-26.xlsx (941 rows: 1 header + 940 data)

**Key columns:**
- SerialNo: Unit serial number
- BomNo: Bill of materials number (CRS0000675 = LT, CRS0000674 = MT)
- TestDate: When the unit was tested
- OverallPassFail: Pass or Fail
- 12 measurement columns (G through R):
  - Suction Tube Temperature
  - Evap Inlet Return Bend A Temperature
  - Evap Inlet Return Bend B Temperature
  - Evap Outlet Air Temperature
  - Evap B Outlet Air Temperature
  - Inlet/Outlet Air Temperature Delta
  - Inlet/Outlet B Air Temperature Delta
  - Ambient Temperature
  - Startup Voltage
  - Final Voltage
  - Startup Current
  - Final Current

**Data composition:**
- 378 LT units (CRS0000675)
- 562 MT units (CRS0000674)
- 619 Pass, 321 Fail overall

### 2.3 Key Requirements

1. **Formula-driven:** Every calculated value must come from an Excel formula, not hardcoded numbers
2. **Auditable:** Users must be able to click any cell and trace the formula back to source data
3. **Visual:** Charts showing bell curves with distribution overlay
4. **Pass-only filtering:** Tolerance bands should use only passing units
5. **Outlier identification:** Clear visual marking of statistical outliers
6. **Multi-method:** Provide multiple tolerance band approaches for comparison

---

## Part 3: Solution Architecture

### 3.1 Architecture Overview

The solution uses a **helper sheet decomposition pattern**:

```
Raw Data (940 rows × 59 columns)
    ↓
    ├→ _Helpers Sheet (hidden, 940 rows × 48 columns)
    │   └─ Per-row IF formulas that return value if conditions met, else ""
    │
    ├→ Config Sheet (24 rows × 11 columns)
    │   └─ Uses simple MIN(), MAX(), AVERAGE(), STDEV() on helper columns
    │
    ├→ Hist Data Sheets (LT and MT, 360 rows each = 12 measurements × 30 bins)
    │   └─ Uses COUNTIFS() to bin data, NORMDIST() for curve
    │
    ├→ Charts (2 sets of 12 charts, one per unit type)
    │   └─ Stacked bar chart (Normal/Warning/Outlier) + line overlay
    │
    └→ Tolerance_Bands Sheet (24 rows × 14 columns)
        └─ Compares three methods: 3-sigma, percentile, IQR
```

### 3.2 Why a Helper Sheet?

**The Problem:**
Filtering and aggregating data in Excel without CSE array formulas is difficult. Functions like MINIFS/MAXIFS don't exist in older Excel versions. Attempts to use:
- MINIFS/MAXIFS → Excel 2019+ only (users have 2010/2013)
- AGGREGATE with division trick → Returns 0 silently
- CSE array formulas (MIN(IF())) → #NAME? errors

**The Solution:**
Decompose the problem into simple steps:
1. **Helper sheet:** One column per (unit, measurement, filter) combination
   - Each cell contains a simple IF formula: "If this row matches criteria, return the value, else return empty string"
   - Empty strings are ignored by MIN(), MAX(), PERCENTILE(), etc.
2. **Config/Tolerance sheets:** Use basic aggregation functions on helper columns
   - MIN(_Helpers!A$2:A$941)
   - AVERAGE(_Helpers!C$2:C$941)
   - PERCENTILE(_Helpers!C$2:C$941, 0.01)

**Result:** Works in Excel 2007 and later, fully auditable, no complex tricks.

### 3.3 The Eight Sheets

| Sheet Name | Purpose | Hidden? | Rows | Columns |
|------------|---------|---------|------|---------|
| RawData | Source data + z-score formulas | No | 941 | 59 |
| _Helpers | Conditional value filters | Yes | 941 | 48 |
| Config | Aggregated statistics | No | 24 | 11 |
| LT_HistData | Histogram bins for LT unit | No | 362 | 8 |
| MT_HistData | Histogram bins for MT unit | No | 362 | 8 |
| LT_BellCurves | Chart workspace | No | (chart only) | — |
| MT_BellCurves | Chart workspace | No | (chart only) | — |
| Tolerance_Bands | Three tolerance methods | No | 24 | 14 |
| Outliers | Convenience view of outliers | No | 400+ | 9 |

---

## Part 4: Step-by-Step Implementation

### Step 1: Load and Prepare Raw Data

**Goal:** Read the source Excel file and add a helper column (UnitType) that maps BomNo to unit type.

**Input:** Run test data start to 4-27-26.xlsx

**Process:**
```python
df = pd.read_excel(DATA_FILE, engine="openpyxl")
df["UnitType"] = df["BomNo"].map({"CRS0000675": "LT", "CRS0000674": "MT"})
df["TestDate"] = pd.to_datetime(df["TestDate"], errors="coerce")
```

**Output:** Pandas DataFrame with all original columns plus UnitType and cleaned TestDate

**Why:** The BomNo is a code; UnitType is human-readable and used in all filtering logic.

---

### Step 2: Create RawData Sheet

**Goal:** Write all source data to the Excel workbook, add z-score formulas for outlier identification.

**Input:** Pandas DataFrame from Step 1

**Process:**
1. Write columns A–F: SerialNo, BomNo, UnitType, ModelNo, TestDate, OverallPassFail
2. Write columns G–R: 12 measurement values (as-is from source)
3. Add columns S–AD: Z-score formulas for each measurement
   - Formula: `=IFERROR((G2-Config!$F$2)/Config!$G$2, "")`
   - References Config sheet mean and stdev (computed later)
4. Add conditional formatting: Red fill on cells where z-score > 3

**Output:** RawData sheet, 941 rows × 30+ columns

**Why columns S–AD (z-scores)?** 
- Allows visual scanning for outliers in the raw data
- Red highlighting makes them obvious
- Formulas reference Config sheet, so they update if statistics change

---

### Step 3: Create _Helpers Sheet (Hidden)

**Goal:** Create filtered value columns that will feed aggregation functions.

**Input:** RawData sheet (from Step 2)

**Process:**

For each of 12 measurements and each of 4 filter types (LT-all, MT-all, LT-pass, MT-pass):
1. Add a column header describing the filter (e.g., "LT_SuctionTemp_All")
2. Add a formula in row 2:
   ```
   =IF(AND(RawData!$C2="LT", RawData!G2<>0), RawData!G2, "")
   ```
   Where:
   - RawData!$C2 = UnitType (column C, row 2)
   - RawData!G2 = measurement value (column G, row 2)
   - "$C" (absolute column, relative row) = copy formula down but always check same column
   - "G2" (relative) = copy formula down and adjust to next measurement column
3. Copy formula down to row 941
4. Repeat for other 47 helper columns
5. Set worksheet.sheet_state = 'hidden'

**Result:** 48 columns × 940 rows of formulas

**Example helper column (LT_SuctionTemp_All):**
- Row 2: Has LT unit and non-zero Suction Temp → returns the temp value
- Row 3: Has MT unit → returns ""
- Row 4: Has LT unit but zero Suction Temp → returns ""

**Output:** _Helpers sheet (hidden)

**Why hidden?** It's purely supporting logic; users don't need to see it, but they can unhide to debug.

---

### Step 4: Create Config Sheet

**Goal:** Compute aggregated statistics for each measurement and unit type using helper sheet data.

**Input:** _Helpers sheet (from Step 3)

**Process:**

Create a table with 24 rows (12 measurements × 2 units):

| Column | Formula | Description |
|--------|---------|-------------|
| Unit | LT or MT | Unit type |
| Measurement | Name | e.g., "Suction Tube Temp" |
| n_all | COUNT(_Helpers!$A$2:$A$941) | Count of numeric values (LT-all helper) |
| n_pass | COUNT(_Helpers!$C$2:$C$941) | Count in LT-pass helper |
| Mean_pass | IFERROR(AVERAGE(_Helpers!$C$2:$C$941),0) | Mean of passing units only |
| StdDev_pass | IFERROR(STDEV(_Helpers!$C$2:$C$941),0) | Std dev of passing units |
| Min_all | IFERROR(MIN(_Helpers!$A$2:$A$941),0) | Minimum across all units |
| Max_all | IFERROR(MAX(_Helpers!$A$2:$A$941),0) | Maximum across all units |
| BinWidth | IFERROR(($I2-$H2+$G2)/30,1) | (Max−Min+σ)/30 for 30 bins |
| BinStart | =$H2-0.5*$G2 | Min − 0.5×σ (extends below min) |
| RawDataCol | G, H, I, ... | Which column in RawData has this measurement |

**Key design decisions:**

1. **Mean and StdDev use pass-only data** (columns C in helpers = LT-pass)
   - This prevents failing units from skewing what "normal" looks like
   
2. **Min and Max use all data** (columns A in helpers = LT-all)
   - Shows the full range of observed values, even if some came from failing units
   - Provides histogram bounds that include all data

3. **30 bins is hardcoded**
   - Provides good detail without over-fragmenting data
   - Works well with ~600 LT units, ~900 MT units

**Output:** Config sheet with 24 data rows, all formulas

**Why these specific formulas?**
- AVERAGE() ignores empty strings (returns of 0 from failed IF checks)
- MIN() and MAX() ignore empty strings too
- STDEV() same
- By referencing helper columns, all filtering logic is transparent and auditable

---

### Step 5: Create Histogram Data Sheets (LT_HistData and MT_HistData)

**Goal:** Create histogram bins for each measurement, showing count per bin and normal distribution curve.

**Input:** Config sheet (Step 4), RawData sheet (Step 2)

**Process:**

For each unit type (LT, MT):
1. Create a sheet with 360 rows (12 measurements × 30 bins per measurement)
2. For each measurement (rows 1–30, 31–60, etc.):
   - Bin boundaries: Calculate BinLo, BinHi, BinCenter
   - Formula for BinCenter row k: `=Config!$K$2 + (k-1)*Config!$J$2 + Config!$J$2/2`
     - Config!$K$2 = BinStart
     - Config!$J$2 = BinWidth
   - TotalCount (all units in this bin):
     ```
     =COUNTIFS(RawData!$C$2:$C$941,"LT", RawData!G$2:G$941,">="&$B2, 
              RawData!G$2:G$941,"<"&$C2, RawData!G$2:G$941,"<>0")
     ```
     Where:
     - RawData!$C = UnitType column
     - RawData!G = measurement column (absolute row range, relative column for copying across)
     - ">="&$B2 and "<"&$C2 = bin boundaries
     - "<>0" = exclude zero values

3. Zone columns (Normal, Warning, Outlier):
   - For each bin row, calculate how many values fall in each zone:
     - **Normal** (within 2σ): |Z| ≤ 2
     - **Warning** (2σ to 3σ): 2 < |Z| ≤ 3
     - **Outlier** (>3σ): |Z| > 3
   - Use IF statements to check z-score of bin center:
     ```
     =IF(ABS(($A2-Config!$F$2)/Config!$G$2)<=2, TotalCount, 0)
     ```
     (Similar logic for Warning and Outlier with different thresholds)

4. CurveY column (normal distribution overlay):
   ```
   =IFERROR(NORMDIST($A2, Config!$F$2, Config!$G$2, FALSE)*Config!$D$2*Config!$J$2, 0)
   ```
   Where:
   - $A2 = bin center
   - Config!$F$2 = mean
   - Config!$G$2 = stdev
   - FALSE = probability density (not cumulative)
   - Config!$D$2 = n_pass (scaling factor)
   - Config!$J$2 = BinWidth (area of each bin)

**Output:** LT_HistData and MT_HistData sheets

**Why this structure?**
- Each bin row contains all data needed to draw that bin
- CurveY is scaled to match the histogram (density × sample size × bin width)
- Three zone columns allow stacked bar chart with color coding

---

### Step 6: Create Charts (LT_BellCurves and MT_BellCurves)

**Goal:** Create 12 stacked bar charts per unit type, one per measurement.

**Input:** LT_HistData and MT_HistData sheets (Step 5)

**Process:**

For each of 12 measurements in each unit type:
1. Create a stacked bar chart using:
   - X-axis: BinCenter (the bin positions)
   - Y-axis Series 1: Normal zone (blue, #4472C4)
   - Y-axis Series 2: Warning zone (orange, #ED7D31)
   - Y-axis Series 3: Outlier zone (red, #C00000)
2. Add a secondary Y-axis with a line chart:
   - Series: CurveY (red line)
   - Shows the theoretical normal distribution curve
3. Format:
   - Title: Measurement name, unit type
   - X-axis label: Measurement units (°F, V, A, etc.)
   - Y-axis label: Count
4. Place chart in appropriate position on LT_BellCurves or MT_BellCurves sheet

**Visual result:**
- Histogram shows actual data distribution
- Three color zones show proximity to outlier threshold
- Red line overlay shows theoretical normal distribution
- Good fit = line passes through histogram nicely
- Poor fit = line doesn't match = data is non-normal

**Output:** 24 charts total (2 sheets × 12 measurements each)

---

### Step 7: Create Tolerance_Bands Sheet

**Goal:** Compute and compare three tolerance band methods.

**Input:** Config sheet (Step 4), _Helpers sheet (Step 3)

**Process:**

Create a table with 24 rows (12 measurements × 2 units):

| Columns | Formulas | Description |
|---------|----------|-------------|
| Unit, Measurement | — | Identifiers |
| n_pass | =Config!$D$2 | From Config sheet |
| Mean | =Config!$F$2 | From Config sheet |
| StdDev | =Config!$G$2 | From Config sheet |
| 3σ_Low | =Config!$F$2 - 3*Config!$G$2 | Mean − 3×StdDev |
| 3σ_High | =Config!$F$2 + 3*Config!$G$2 | Mean + 3×StdDev |
| P1_Low | =IFERROR(PERCENTILE(_Helpers!$C$2:$C$941,0.01),"") | 1st percentile |
| P99_High | =IFERROR(PERCENTILE(_Helpers!$C$2:$C$941,0.99),"") | 99th percentile |
| IQR_Low | =IFERROR(QUARTILE(_Helpers!$C$2:$C$941,1) - 1.5*(QUARTILE(...,3)-QUARTILE(...,1)),"") | Q1 − 1.5×IQR |
| IQR_High | =IFERROR(QUARTILE(_Helpers!$C$2:$C$941,3) + 1.5*(QUARTILE(...,3)-QUARTILE(...,1)),"") | Q3 + 1.5×IQR |
| Rec_Low | =IFERROR(MAX(3σ_Low, P1_Low, IQR_Low),"") | Recommended low (most conservative) |
| Rec_High | =IFERROR(MIN(3σ_High, P99_High, IQR_High),"") | Recommended high (most conservative) |
| Spread_Ratio | Ratio of ranges | How different the methods are |
| Agreement | Qualitative | High/Medium/Low agreement |

**Interpretation:**
- **3-Sigma:** Widest range (captures ~99.7%), assumes normality
- **Percentile:** Empirical (data-driven), captures 98% of observed data
- **IQR (Tukey):** Most conservative, focuses on central 50% with margin
- **Rec (Recommended):** Takes the intersection (most restrictive) of all three

**Why three methods?**
1. Different assumptions (parametric vs. empirical vs. distribution-free)
2. Helps identify when methods agree (high confidence) vs. disagree (investigate)
3. IQR is robust to outliers; 3-Sigma assumes normality; Percentile is empirical

**Output:** Tolerance_Bands sheet with 24 data rows

---

### Step 8: Create Outliers Sheet

**Goal:** Convenience view showing all rows with z-score > 3σ.

**Input:** RawData sheet (Step 2, columns with z-scores)

**Process:**

This sheet is computed via Python during build (not live formulas):
1. Read RawData sheet
2. For each measurement, find rows where z-score > 3
3. Create a table with columns:
   - SerialNo, UnitType, BomNo, TestDate, OverallPassFail
   - Measurement (which of the 12)
   - Value (the actual measurement)
   - Z_Score (the z-score for that value)

**Output:** Outliers sheet, 400+ rows typically

**Why Python instead of formulas?**
- Easier to reshape data from wide (12 measurement columns) to long (1 measurement per row)
- Filtering and sorting is simpler
- Still fully auditable: anyone can recompute by reading RawData z-score columns

---

## Part 5: Formula Details

### 5.1 Helper Sheet Formulas

**Pattern:** `=IF(AND(condition1, condition2, ...), value, "")`

**Example: LT unit, Suction Tube Temp, all data**
```
=IF(AND(RawData!$C2="LT", RawData!G2<>0), RawData!G2, "")
```

**Example: MT unit, Suction Tube Temp, pass-only data**
```
=IF(AND(RawData!$C2="MT", RawData!E2="Pass", RawData!G2<>0), RawData!G2, "")
```

**Key points:**
- `$C` = absolute column C (doesn't change when copied right)
- `2` = relative row 2 (changes to 3, 4, 5 when copied down)
- This allows copying the formula both down (different rows) and right (different measurements)
- Empty string `""` is ignored by MIN, MAX, AVERAGE, STDEV, PERCENTILE, QUARTILE
- Non-zero check (`<>0`) prevents zero measurements from affecting statistics

### 5.2 Config Sheet Formulas

**Count all data:**
```
=COUNT(_Helpers!$A$2:$A$941)
```
Counts numeric values in helper column A (LT-all). Empty strings aren't counted.

**Average pass-only:**
```
=IFERROR(AVERAGE(_Helpers!$C$2:$C$941), 0)
```
AVERAGE of helper column C (LT-pass). IFERROR returns 0 if no values (empty sheet case).

**Standard deviation:**
```
=IFERROR(STDEV(_Helpers!$C$2:$C$941), 0)
```
STDEV is legacy equivalent to STDEV.S (sample standard deviation). Ignores empty strings.

**Min and max:**
```
=IFERROR(MIN(_Helpers!$A$2:$A$941), 0)
=IFERROR(MAX(_Helpers!$A$2:$A$941), 0)
```
These use all-data helper columns (A and B for LT, repeated pattern for MT).

**Bin width:**
```
=IFERROR(($I2-$H2+$G2)/30, 1)
```
Where $H2=Min, $I2=Max, $G2=StdDev. Formula: (Max − Min + StdDev) / 30
- Denominator 30 = hardcoded bin count
- "+StdDev" adds a small margin so histogram extends slightly beyond data range
- Fallback to 1 if division fails

**Bin start:**
```
=$H2-0.5*$G2
```
Min − 0.5×StdDev. Starts histogram slightly before the minimum value.

### 5.3 Histogram Data Formulas

**Bin center:**
```
=Config!$K$2 + (ROW()-2)*Config!$J$2 + Config!$J$2/2
```
Where:
- Config!$K$2 = BinStart
- Config!$J$2 = BinWidth
- (ROW()-2) = bin index (0 for row 2, 1 for row 3, ..., 29 for row 31)
- "+Config!$J$2/2" = offset to center of bin

**Total count in bin:**
```
=COUNTIFS(RawData!$C$2:$C$941,"LT", 
          RawData!G$2:G$941,">="&$B2, 
          RawData!G$2:G$941,"<"&$C2, 
          RawData!G$2:G$941,"<>0")
```
Counts rows where:
1. UnitType (column C) = "LT"
2. Measurement value (column G) ≥ BinLo ($B2)
3. Measurement value < BinHi ($C2)
4. Measurement value is not zero

**Normal zone count (within 2σ):**
```
=IF(ABS(($A2-Config!$F$2)/Config!$G$2)<=2, TotalCount, 0)
```
- $A2 = bin center
- Config!$F$2 = mean
- Config!$G$2 = stdev
- Calculates Z-score of bin center; if |Z| ≤ 2, return TotalCount, else 0
- Means: if entire bin is in normal zone, all its counts go to Normal series

**Warning zone count (2σ to 3σ):**
```
=IF(AND(ABS(($A2-Config!$F$2)/Config!$G$2)>2, 
         ABS(($A2-Config!$F$2)/Config!$G$2)<=3), 
    TotalCount, 0)
```
Similar logic but for 2 < |Z| ≤ 3.

**Outlier zone count (>3σ):**
```
=IF(ABS(($A2-Config!$F$2)/Config!$G$2)>3, TotalCount, 0)
```
For |Z| > 3.

**Curve Y (normal distribution):**
```
=IFERROR(NORMDIST($A2, Config!$F$2, Config!$G$2, FALSE)*Config!$D$2*Config!$J$2, 0)
```
Where:
- $A2 = bin center
- Config!$F$2 = mean (μ)
- Config!$G$2 = stdev (σ)
- FALSE = probability density function (not cumulative)
- Config!$D$2 = n_pass (scales height to sample size)
- Config!$J$2 = BinWidth (scales to bin area)

**Why scale CurveY?**
- NORMDIST(..., FALSE) returns the probability density at the value
- To match histogram height, multiply by sample size (n_pass) and bin width
- Result: a curve that peaks at approximately the same height as the histogram

### 5.4 Tolerance_Bands Formulas

**3-Sigma Low and High:**
```
=Config!$F$2 - 3*Config!$G$2
=Config!$F$2 + 3*Config!$G$2
```
Mean ± 3 standard deviations.

**Percentile Low and High (1st and 99th):**
```
=IFERROR(PERCENTILE(_Helpers!$C$2:$C$941, 0.01), "")
=IFERROR(PERCENTILE(_Helpers!$C$2:$C$941, 0.99), "")
```
PERCENTILE is legacy equivalent to PERCENTILE.INC. Looks up percentile value in pass-only helper data.

**Quartile Low and High (IQR method):**
```
=IFERROR(QUARTILE(_Helpers!$C$2:$C$941, 1) - 
         1.5*(QUARTILE(_Helpers!$C$2:$C$941, 3) - 
              QUARTILE(_Helpers!$C$2:$C$941, 1)), "")

=IFERROR(QUARTILE(_Helpers!$C$2:$C$941, 3) + 
         1.5*(QUARTILE(_Helpers!$C$2:$C$941, 3) - 
              QUARTILE(_Helpers!$C$2:$C$941, 1)), "")
```
QUARTILE parameters: 1=Q1 (25th percentile), 3=Q3 (75th percentile).
IQR = Q3 − Q1 (interquartile range).
Tukey fences = Q1 − 1.5×IQR to Q3 + 1.5×IQR.

**Recommended Low and High (most conservative):**
```
=IFERROR(MAX(3σ_Low, P1_Low, IQR_Low), "")
=IFERROR(MIN(3σ_High, P99_High, IQR_High), "")
```
Takes the highest lower bound and lowest upper bound → most restrictive range that all methods agree on.

---

## Part 6: Function Compatibility

### 6.1 The Problem

The workbook must work in Excel 2007 through current versions. Different versions support different functions.

**Functions that cause compatibility issues:**

| Newer Name | Legacy Name | First Available | Issue |
|------------|------------|-----------------|-------|
| NORM.DIST | NORMDIST | Excel 97 | Dot-named functions not recognized without _xlfn. prefix |
| PERCENTILE.INC | PERCENTILE | Excel 97 | Same issue |
| QUARTILE.INC | QUARTILE | Excel 97 | Same issue |
| MINIFS | — | Excel 2019 | Doesn't exist in older versions |
| MAXIFS | — | Excel 2019 | Doesn't exist in older versions |
| STDEV.S | STDEV | Excel 97 | Legacy name works everywhere |
| AVERAGE | — | Excel 97 | No issues |
| COUNT | — | Excel 97 | No issues |

### 6.2 The Root Cause

When openpyxl writes formulas to Excel, it uses the function names as-is. For newer functions with dots (NORM.DIST), Excel internally represents these with a prefix:
```
_xlfn.NORM.DIST(args)
```

The `_xlfn.` prefix tells Excel "this is a newer function, convert it to the appropriate legacy name if needed."

**Problem:** openpyxl doesn't automatically add this prefix. When Excel 2010 opens a file with `NORM.DIST` (without prefix), it doesn't recognize the function name → #NAME? error.

### 6.3 The Solution

Use legacy function names that have existed since Excel 97:
- NORMDIST instead of NORM.DIST
- PERCENTILE instead of PERCENTILE.INC
- QUARTILE instead of QUARTILE.INC

These names are synonymous with the newer dot-named versions in modern Excel. They work in all versions from Excel 97 onward.

### 6.4 Implementation in Code

In `build_eol_workbook.py`, all formulas use legacy names:

```python
# Correct (uses legacy function):
curve_formula = f'=IFERROR(NORMDIST($A2,Config!$F$2,Config!$G$2,FALSE)*Config!$D$2*Config!$J$2,0)'

# Wrong (uses dot-named function, may cause #NAME? errors):
curve_formula = f'=IFERROR(NORM.DIST($A2,Config!$F$2,Config!$G$2,FALSE)*Config!$D$2*Config!$J$2,0)'

# Correct (uses legacy PERCENTILE):
percentile_low = f'=IFERROR(PERCENTILE(_Helpers!$C$2:$C$941,0.01),"")'

# Wrong (uses PERCENTILE.INC):
percentile_low = f'=IFERROR(PERCENTILE.INC(_Helpers!$C$2:$C$941,0.01),"")'
```

### 6.5 Testing Compatibility

To verify the workbook opens correctly in an older Excel version:
1. Open the workbook in Excel 2010 or 2013
2. Open any histogram sheet (LT_HistData or MT_HistData)
3. Click on a cell in the "CurveY" column
4. Verify the formula bar shows the formula (not #NAME? error)
5. Spot-check a few Config sheet formulas

---

## Part 7: Usage Instructions

### 7.1 Opening and Exploring the Workbook

**File location:** `EOL_BellCurves_v3g.xlsx`

**To open:**
1. File → Open → select EOL_BellCurves_v3g.xlsx
2. Click "Enable Content" if prompted (normal for macro-free workbooks)

**Sheets overview:**
- **Config:** Start here to understand statistics (mean, stdev, min, max per measurement)
- **LT_BellCurves, MT_BellCurves:** Visual representation; easy to spot outliers and distribution shape
- **Tolerance_Bands:** Recommended acceptable ranges per measurement
- **RawData:** Source data with z-scores highlighted in red if >3σ
- **_Helpers:** Hidden; unhide to audit the helper formulas (right-click sheet tab → Unhide)

### 7.2 Understanding the Bell Curves Sheet

Each chart shows one measurement for one unit type (e.g., "Suction Tube Temp — LT Unit").

**Visual elements:**
- **Stacked bars:** Histogram showing count per value range
  - Blue (lower part) = "Normal" (within 2σ)
  - Orange (middle part) = "Warning" (between 2σ and 3σ)
  - Red (top part) = "Outlier" (beyond 3σ)
- **Red line:** Theoretical normal distribution curve (for reference)

**What to look for:**
- **Good fit:** Bars roughly follow the red curve → data is approximately normal
- **Poor fit:** Bars deviate significantly from the curve → data is skewed or multimodal
- **Red (outlier) bars:** Indicate unusual measurements; investigate units with these values

### 7.3 Interpreting the Tolerance_Bands Sheet

**Three methods shown per measurement:**

| Method | Range | Captures | Use When |
|--------|-------|----------|----------|
| 3-Sigma | Mean ± 3σ | ~99.7% | You trust normal distribution assumption |
| Percentile | 1st to 99th %ile | 98% of data | You want data-driven bounds |
| IQR (Tukey) | Q1−1.5×IQR to Q3+1.5×IQR | Central data | You want robustness to outliers |

**Recommended column:** Takes the most conservative (tightest) bounds across all three methods.

**To use for quality control:**
1. Set tolerance bands for each measurement using the "Recommended" column
2. Test incoming units: if measurement falls outside recommended range, flag for review
3. If all three methods agree closely, recommendation is high-confidence
4. If methods disagree significantly, investigate why (data may be non-normal)

### 7.4 Tracing a Formula

**Example: What is the mean Suction Tube Temperature for LT units?**

1. Open Config sheet
2. Find row for "Suction Tube Temp, LT"
3. Click cell in "Mean_pass" column
4. Formula bar shows: `=IFERROR(AVERAGE(_Helpers!$C$2:$C$941),0)`
5. This says: "Average the values in _Helpers column C, rows 2-941, or return 0 if no data"
6. To see what's in _Helpers column C:
   - Right-click _Helpers sheet tab → Unhide → OK
   - Go to _Helpers sheet
   - Column C (header says "LT_SuctionTemp_Pass")
   - This column contains:
     - Actual temperature if row is LT unit AND passed AND temp ≠ 0
     - Blank ("") otherwise
7. To verify one value:
   - Click any cell in _Helpers column C (e.g., C2)
   - Formula bar shows: `=IF(AND(RawData!$C2="LT", RawData!$E2="Pass", RawData!G2<>0), RawData!G2, "")`
   - Click RawData!$C2 → goes to RawData sheet, row 2, column C (UnitType)
   - Verify it's "LT"
   - Click RawData!$E2 → row 2, column E (OverallPassFail)
   - Verify it's "Pass"
   - Click RawData!G2 → row 2, column G (Suction Tube Temp)
   - This is the actual measurement value

**Result:** Full traceability from Config mean → Helper columns → RawData source

### 7.5 Common Questions

**Q: Why are some measurements blank in the Tolerance_Bands sheet?**
A: Usually means less than 5 passing units for that unit type + measurement combination. Insufficient data to compute meaningful statistics.

**Q: A chart looks empty or has no curve line. Why?**
A: Could be:
1. All values are zero (rare)
2. Insufficient data (less than 5 non-zero measurements)
3. All values are identical (stdev = 0, curve can't be drawn)

Check Config sheet for that measurement: is n_pass ≥ 5 and StdDev > 0?

**Q: The recommended tolerance range seems too narrow/wide. Should I trust it?**
A: Check the "Agreement" column in Tolerance_Bands (if present, or compare the three methods):
- All three methods give similar ranges → high confidence, use the recommendation
- Methods disagree significantly → data may be non-normal; consult a statistician

**Q: How do I update the workbook with new test data?**
A: This is a generated workbook. To add new data:
1. Update the source file: Run test data start to 4-27-26.xlsx
2. Re-run `python build_eol_workbook.py`
3. Open the new EOL_BellCurves_vXX.xlsx

Do not manually edit formulas in the workbook; regenerate instead.

### 7.6 File Size and Performance

- **File size:** ~2-3 MB (mostly formulas in _Helpers and HistData sheets)
- **Calculation time:** 5-10 seconds on typical modern Excel
- **To speed up:** Tools → Options → Formulas → Change calculation to Manual, press F9 to recalculate

---

## Appendix: Python Implementation Details

### A.1 build_eol_workbook.py Structure

```python
def load():
    # Read source file, map BomNo to UnitType

def build_rawdata(wb):
    # Write RawData sheet with formulas for z-scores

def build_helpers(wb):
    # Create _Helpers sheet with 48 columns of IF formulas

def build_config(wb):
    # Create Config sheet with aggregation formulas

def build_histdata(wb):
    # Create LT_HistData and MT_HistData sheets

def build_charts(wb):
    # Create 24 charts (12 per unit type)

def build_tolerance(wb):
    # Create Tolerance_Bands sheet

def build_outliers(wb):
    # Create Outliers sheet (Python-computed, not formulas)

def main():
    # Orchestrate all steps
    df = load()
    wb = openpyxl.Workbook()
    build_rawdata(wb)
    build_helpers(wb)
    build_config(wb)
    build_histdata(wb)
    build_charts(wb)
    build_tolerance(wb)
    build_outliers(wb)
    wb.save('EOL_BellCurves_vXX.xlsx')
```

### A.2 Why Each Design Choice

| Choice | Reason |
|--------|--------|
| Helper sheet pattern | Conditional aggregation without CSE arrays or modern functions |
| 30 bins | Balances detail vs. over-fragmentation for ~900 records |
| Pass-only mean/stdev | Failing units shouldn't skew "normal" statistics |
| All-data min/max | Shows full observed range, even from outliers |
| Three tolerance methods | Provides confidence via agreement; different assumptions |
| Legacy function names | Works in Excel 2007+; no compatibility issues |
| Z-score highlighting in RawData | Quick visual scan for outliers without charts |
| Hidden _Helpers sheet | Reduces clutter; still available for auditing |
| Chart overlay (bars + curve) | Shows both empirical and theoretical distributions |

---

## Summary

The EOL Bell Curves workbook transforms raw end-of-line test data into actionable insights:

1. **Loads** test data for LT and MT condensing units
2. **Filters** data using a helper sheet pattern to separate unit types and pass/fail status
3. **Computes** statistics using simple Excel functions on filtered data
4. **Visualizes** distributions as histograms with bell curve overlays
5. **Identifies** outliers using z-score and percentile methods
6. **Recommends** tolerance bands using three comparative methods

All calculations are formula-driven, fully auditable, and compatible with Excel 2007+.

---

**Document Version:** 1.0  
**Last Updated:** May 4, 2026  
**Workbook Version:** v3g
