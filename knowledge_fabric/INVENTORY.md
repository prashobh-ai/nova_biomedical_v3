# Knowledge Fabric — corpus inventory

*Generated 2026-08-04 07:01 UTC by `scripts/build_inventory.py`. Do not edit by hand.*

Every file listed here is in this repository and can be opened. Every total is a count of those files. Reproduce with `python scripts/verify_corpus.py --deep`.

## What is in the corpus

| Source | Files on disk | Indexed records | Size |
|---|---:|---:|---:|
| Product manuals (PDF) | 20 | 20 | 102.4 MB |
| FDA 510(k) documents (PDF) | 62 | 62 | 34.3 MB |
| FDA structured exports (CSV) | 9 | 359 | 2.1 MB |
| YouTube videos (channel) | 79 | 79 | metadata + transcripts |
| **Total** | **91 files** | **520 records** | **138.8 MB** |

### Reading the two count columns

They differ on purpose, and the difference is the honest part.

- A **PDF** is one file and one record. 82 documents on disk, 82 in the index.
- The **CSV exports** hold thousands of rows; the fabric selects 359 of them as retrievable records — clearances, recalls, classifications and enforcement actions relevant to these products. The rest stay in the repo unindexed.
- A **video** is one record for its publisher-written metadata, plus one record per transcript segment once transcribed.

So "520 records" means 82 documents + 359 regulatory records + 79 video records — not 520 PDFs. The dashboard says *records*, never *documents*, for exactly this reason.

## What the build derives from it

| Artifact | Count | Where it comes from |
|---|---:|---|
| Retrievable passages (chunks) | 3551 | documents packed to ~700 chars; structured rows stay atomic |
| Entities | 416 | products, analytes, clearances, product codes extracted at build time |
| Relationships (graph edges) | 446 | typed co-occurrence between entities |
| Lexical vocabulary (BM25) | 13308 | distinct terms across all passages |
| Embeddings | 3551 x 96 dims | tfidf+truncated_svd(lsa), 42.4% variance retained |
| Term vectors | 6000 x 96 dims | LSA vocabulary of 6000 terms |
| Cross-source products | 11 | products appearing in more than one source system |

## Product manuals

| File | Product | Type | Size |
|---|---|---|---:|
| `BioProfile_FAST_CDV__LPN_65655_C.pdf` | BioProfile FAST CDV | IFU Manual | 5.1 MB |
| `BioProfile_FLEX2__LPN_57960.pdf` | BioProfile FLEX2 | IFU Manual | 10.0 MB |
| `BioProfile_FLEX2__LPN_59698.pdf` | BioProfile FLEX2 | IFU Manual | 4.8 MB |
| `BioProfile_FLEX2__LPN_62541_E.pdf` | BioProfile FLEX2 | IFU Manual | 31.9 MB |
| `BioProfile_pHOx__IFU_52942.pdf` | BioProfile pHOx | IFU Manual | 3.3 MB |
| `Lactate_Plus_Xpress2_IFU.pdf` | — | Instructions For Use | 5.1 MB |
| `Nova_Primary_Glucose_Analyzer__LPN_63438.pdf` | Nova Primary Glucose Analyzer | IFU Manual | 3.7 MB |
| `StatSensor_Creatinine_IFU_Instruction_Manual.pdf` | — | Instructions For Use | 2.8 MB |
| `StatSensor_Creatinine_Reference_Manual.pdf` | — | Instructions For Use | 1.0 MB |
| `StatStrip_2.0_Glucose_Quick_Reference_Guide.pdf` | — | Instructions For Use | 2.5 MB |
| `StatStrip_Glucose_Hospital_Gen_1_86__LPN_55848_M.pdf` | StatStrip Glucose Hospital (Gen 1.86) | IFU Manual | 4.1 MB |
| `StatStrip_Glucose_Hospital_Gen_2__LPN_65965_D.pdf` | StatStrip Glucose Hospital (Gen 2) | IFU Manual | 5.5 MB |
| `StatStrip_Glucose_Quick_Reference_Guide.pdf` | — | Instructions For Use | 1.7 MB |
| `StatStrip_Lactate_IFU_Instruction_Manual.pdf` | — | Instructions For Use | 4.2 MB |
| `StatStrip_Lactate_Reference_Manual.pdf` | — | Instructions For Use | 1.5 MB |
| `StatStrip_Xpress2_Glucose_Reference_Manual.pdf` | — | Instructions For Use | 710 KB |
| `StatStrip_Xpress2_Glucose__LPN_57577_G.pdf` | StatStrip Xpress2 Glucose | IFU Manual | 1.7 MB |
| `Stat_Profile_Prime_CCS__LPN_52920.pdf` | Stat Profile Prime CCS | IFU Manual | 3.3 MB |
| `Stat_Profile_Prime_ES_Comp_Plus__LPN_62064.pdf` | Stat Profile Prime ES Comp Plus | IFU Manual | 4.7 MB |
| `Stat_Profile_Prime_Plus__LPN_60278_E.pdf` | Stat Profile Prime Plus | IFU Manual | 4.7 MB |

## FDA 510(k) documents

62 clearance and review documents, each fetched from `accessdata.fda.gov`. Full URLs and checksums are in `SOURCES.csv`.

<details><summary>Full list</summary>

| File | Size |
|---|---:|
| `K041016.pdf` | 15 KB |
| `K060345.pdf` | 303 KB |
| `K061830.pdf` | 106 KB |
| `K063821.pdf` | 134 KB |
| `K070068.pdf` | 208 KB |
| `K070255.pdf` | 32 KB |
| `K070960.pdf` | 10 KB |
| `K091547.pdf` | 217 KB |
| `K100602.pdf` | 178 KB |
| `K101633.pdf` | 148 KB |
| `K110648.pdf` | 309 KB |
| `K112638.pdf` | 276 KB |
| `K112955.pdf` | 180 KB |
| `K122435.pdf` | 258 KB |
| `K122688.pdf` | 317 KB |
| `K131013.pdf` | 311 KB |
| `K131703.pdf` | 419 KB |
| `K132121.pdf` | 596 KB |
| `K141907.pdf` | 307 KB |
| `K142220.pdf` | 356 KB |
| `K150281.pdf` | 371 KB |
| `K150461.pdf` | 346 KB |
| `K151982.pdf` | 1.5 MB |
| `K152986.pdf` | 399 KB |
| `K160156.pdf` | 262 KB |
| `K160990.pdf` | 106 KB |
| `K161856.pdf` | 392 KB |
| `K163490_REVIEW_StatStrip_Xpress_2_Glucose_Hospital_Meter_System.pdf` | 232 KB |
| `K163490_StatStrip_Xpress_2_Glucose_Hospital_Meter_System.pdf` | 1.7 MB |
| `K170464.pdf` | 157 KB |
| `K171059.pdf` | 426 KB |
| `K173797.pdf` | 123 KB |
| `K180186.pdf` | 146 KB |
| `K180340.pdf` | 139 KB |
| `K180428.pdf` | 177 KB |
| `K181043_REVIEW_StatStrip_Glucose_Hospital_Meter_System.pdf` | 355 KB |
| `K181043_StatStrip_Glucose_Hospital_Meter_System.pdf` | 238 KB |
| `K182549.pdf` | 192 KB |
| `K182552.pdf` | 184 KB |
| `K191365.pdf` | 492 KB |
| `K191626_REVIEW_Stat_Profile_Prime_ES_Comp_Plus_Analyzer_System.pdf` | 177 KB |
| `K191626_Stat_Profile_Prime_ES_Comp_Plus_Analyzer_System.pdf` | 1.1 MB |
| `K193246_REVIEW_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 88 KB |
| `K193246_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 300 KB |
| `K200204.pdf` | 350 KB |
| `K200349.pdf` | 341 KB |
| `K200403_REVIEW_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 122 KB |
| `K200403_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 311 KB |
| `K203549_Nova_Primary_Glucose_Analyzer_System.pdf` | 431 KB |
| `K203549_REVIEW_Nova_Primary_Glucose_Analyzer_System.pdf` | 317 KB |
| `K221326_Nova_Allegro_HbA1c_Assay,_Nova_Allegro_Analyzer.pdf` | 2.7 MB |
| `K221326_REVIEW_Nova_Allegro_HbA1c_Assay,_Nova_Allegro_Analyzer.pdf` | 352 KB |
| `K221813_Nova_Allegro_UACR_Assay,_Nova_Allegro_Analyzer.pdf` | 2.7 MB |
| `K221813_REVIEW_Nova_Allegro_UACR_Assay,_Nova_Allegro_Analyzer.pdf` | 319 KB |
| `K221900_REVIEW_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 445 KB |
| `K221900_Stat_Profile_Prime_Plus_Analyzer_System.pdf` | 2.8 MB |
| `K232075_REVIEW_StatStrip_Glucose_Hospital_Meter_System.pdf` | 242 KB |
| `K232075_StatStrip_Glucose_Hospital_Meter_System.pdf` | 2.7 MB |
| `K251281_Nova_Max_Creat_eGFR_Monitoring_System.pdf` | 2.7 MB |
| `K251281_REVIEW_Nova_Max_Creat_eGFR_Monitoring_System.pdf` | 453 KB |
| `K252206_Nova_Allegro_UACR_Assay,_Nova_Allegro_Analyzer.pdf` | 2.5 MB |
| `K252206_REVIEW_Nova_Allegro_UACR_Assay,_Nova_Allegro_Analyzer.pdf` | 245 KB |

</details>

## FDA structured exports

| File | Rows | Size |
|---|---:|---:|
| `510k_clearances.csv` | 129 | 31 KB |
| `device_recalls.csv` | 36 | 48 KB |
| `enforcement_reports.csv` | 19 | 17 KB |
| `establishment_registrations.csv` | 470 | 82 KB |
| `maude_adverse_events_sample.csv` | 2000 | 1.8 MB |
| `nova_ifu_document_index.csv` | 23 | 5 KB |
| `novabiomedicaldocs_site_structure.csv` | 27 | 4 KB |
| `product_code_classifications.csv` | 32 | 3 KB |
| `udi_device_identifiers.csv` | 500 | 91 KB |

## YouTube channel

- **79** active videos from the company channel
- **79** carry a publication date (79 publisher-asserted)
- **0** transcribed so far
- Publication range: **2019-02-13** to **2026-08-03**
- Withdrawn (tombstoned, retained for supersession checks): **0**

Per-video metadata lives in `knowledge_fabric/youtube/manifest.json`; transcripts in `knowledge_fabric/youtube/transcripts/`.

---

## Verifying this yourself

```bash
python scripts/verify_corpus.py --deep     # checksums every file, reconciles every count
python -m pipeline.build_index             # rebuild the index from source
python scripts/build_inventory.py          # regenerate this file
```

`verify_corpus.py` recounts records from the raw files rather than reading them back out of the index, so a number that only exists in the index cannot pass.

