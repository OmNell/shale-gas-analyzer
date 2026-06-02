# Dataset Folder

Put well production CSV files here.

Examples:

- `X1.csv`
- `X2.csv`

Dataset matching logic:

1. If `well_name` matches a CSV filename, case-insensitive, that file is used.
2. If the filename does not match, the tools inspect `Well_ID` inside each CSV.
3. If `well_name=AUTO` and there is only one CSV, that CSV is used automatically.
4. If there are multiple CSV files and no exact match, the newest modified CSV is used and the tool output will say so.
