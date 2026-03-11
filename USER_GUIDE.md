# CPG Insurance Sorting System — User Guide

This system reads scanned patient requisition forms, checks the insurance against a blocklist of non-participating insurances, and flags cases that need to be sent to a different lab.

---

## 1. Getting Started

1. Open your web browser (Chrome, Edge, or Firefox).
2. Go to `http://localhost:5000` (or the server address your supervisor provided).
3. The **Dashboard** loads automatically. You will see summary cards at the top showing counts for flagged, needs review, poor scan, and clear cases.
4. The dashboard **refreshes every 15 seconds** so you always see the latest results.

---

## 2. Uploading a Scan

1. Find the **Upload Scan** card on the dashboard.
2. Click **Choose File**.
3. Select a scanned requisition from your computer. Accepted formats: **PDF, TIFF, PNG, JPG, BMP**.
4. Click **Process Scan**.
5. The system reads the form, checks the insurance, and shows the result right away.

**Tip:** For best results, scan at **300 DPI or higher** in **black and white** mode.

---

## 3. Understanding the Dashboard

### Status Colors

| Color | Status | What It Means |
|-------|--------|---------------|
| Red | **Flagged** | The insurance is on the blocklist. Action needed. |
| Yellow | **Needs Review** | The system could not determine the insurance with full confidence. A person should check it. |
| Orange | **Poor Scan** | The scan quality was too low to read reliably. The form needs to be re-scanned. |
| Green | **Clear** | The insurance is not on the blocklist. No action needed. |
| Gray | **Handled** | Someone already took care of this case. |
| Red | **Error** | Something went wrong during processing. Try uploading the scan again. |

### Alert Banners

- An **orange banner** appears when a scan has poor quality. This means the system is not confident in what it read.
- A **red banner** means the insurance was matched to the blocklist.

### Scan Quality Column

This column shows how readable the scan was. Higher is better. If the quality is low, re-scan the document for more accurate results.

---

## 4. What to Do When a Case is Flagged

A flagged case means the patient's insurance is **not participating** with this lab.

1. **Pull the physical requisition** from the batch.
2. **Verify the insurance** name on the form matches what the system detected.
3. **Send the requisition to the other lab** per your standard procedure.
4. Come back to the dashboard and click **Mark Handled** on that case so the rest of the team knows it has been taken care of.

---

## 5. What to Do With Poor Scans

A poor scan means the system could not read the form well enough to check the insurance.

1. Find the original paper requisition.
2. **Re-scan it** using these settings:
   - **Resolution:** 300 DPI or higher
   - **Color mode:** Black and white (not color or grayscale)
   - Make sure the page is **straight, fully on the glass, and free of smudges**
3. **Upload the new scan** using the Upload Scan card on the dashboard.
4. The system will process the cleaner version and give you a result.

---

## 6. All Cases View

1. Click **All Cases** in the navigation menu.
2. You will see every requisition the system has processed.
3. Use the **status filter** dropdown to show only flagged, clear, poor scan, or other categories.
4. Use this view to look up a specific case or review history.

---

## 7. How the System Works

When a scan enters the system, it goes through five steps automatically:

```
  Scanned image drops into folder
          │
          ▼
     ┌─────────┐
     │ Tesseract│  ← OCR extracts text + per-word confidence scores
     │   OCR    │
     └────┬─────┘
          │
          ▼
     ┌─────────┐
     │ Quality  │  ← Score < 40%? → "poor_scan" (orange alert)
     │  Check   │     Score 40-78%? → "fair" (extra caution)
     └────┬─────┘
          │
          ▼
     ┌─────────┐
     │  Parser  │  ← Regex extracts: insurance name, member ID, group #
     └────┬─────┘
          │
          ▼
     ┌─────────┐
     │ Matcher  │  ← Checks extracted fields against blocklist CSV
     │          │     Exact name, fuzzy name (85%+), ID prefix match
     └────┬─────┘
          │
          ▼
     ┌─────────┐
     │   DB     │  ← Stores result in SQLite, shows on dashboard
     └─────────┘
```

**Step 1 — OCR:** The system reads the scanned image and converts it to text using optical character recognition. It also scores how confident it is in each word it reads.

**Step 2 — Quality Check:** If the average confidence score is below 40%, the scan is marked as **Poor Scan** and flagged for manual review. If it's between 40-78%, the system treats results with extra caution.

**Step 3 — Parser:** The system looks for key fields on the form — the **insurance name**, **member ID**, and **group number** — using pattern matching.

**Step 4 — Matcher:** The extracted insurance info is compared against the **blocklist** (the list of non-participating insurances). It checks three ways:
- **Exact name match** — the insurance name matches a blocklist entry exactly
- **Fuzzy name match** — the name is close enough (85%+ similarity), which catches minor OCR misreads
- **ID prefix match** — the member ID starts with a known prefix for a non-participating insurer (e.g., "YMM" for BCBS-NC)

**Step 5 — Store & Display:** The result is saved and immediately appears on the dashboard for staff to act on.

---

## 8. Managing the Blocklist

The blocklist is the list of non-participating insurances. When a scanned insurance matches an entry on this list, the case gets flagged.

1. Click the **Blocklist** tab in the navigation menu.
2. You will see all currently blocked insurance names.
3. **To add an insurance:** Type the insurance name in the Add field and click **Add**.
4. **To remove an insurance:** Find it in the list and click **Remove** next to it.

Changes take effect immediately for all new scans. Previously processed cases are not re-checked automatically.

---

## 9. Exporting Reports

1. Click the **Export CSV** button (available on the dashboard or All Cases view).
2. A file will download to your computer containing all processed cases.
3. The report includes: patient info extracted from the scan, insurance name, status, scan quality score, and date processed.
4. You can open this file in Excel for record-keeping or reporting.

---

## 10. Automatic Folder Watching

If your supervisor has set up the folder watcher:

- Any scan file dropped into the **watched folder** is picked up and processed automatically.
- You do **not** need to upload these manually. They will appear on the dashboard on their own.
- This is useful when your scanner saves files directly to a shared folder.

Ask your supervisor which folder is being watched if you are unsure.

---

## 11. Troubleshooting

**The page won't load**
- Make sure the server is running. Ask your supervisor or IT contact.
- Double-check the address in your browser.
- Try refreshing the page.

**A scan won't process**
- Make sure the file is one of the accepted formats: PDF, TIFF, PNG, JPG, or BMP.
- Make sure the file is not empty or corrupted. Try opening it on your computer first.
- Try uploading it again.

**Results seem wrong or insurance name looks garbled**
- The scan quality is probably too low. Re-scan at 300 DPI, black and white, with the page straight on the glass.
- Handwritten forms are harder to read than printed ones. Double-check these manually.

**I can't find a case I just scanned**
- The dashboard refreshes every 15 seconds. Wait a moment and it should appear.
- Check the **All Cases** view and make sure no status filter is hiding it.
- If using the watched folder, confirm the file was saved to the correct location.

**A case is flagged but the insurance looks fine**
- The blocklist may need updating. Check the **Blocklist** tab to see if the insurance is listed there by mistake, and remove it if needed.
- If the system misread the insurance name, click **Needs Review** and verify manually.

---

*For technical issues beyond this guide, contact your supervisor or IT support.*
