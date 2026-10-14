# Third party notices

The project code has no open-source license grant. Public source access does not change the rights
in dependencies, source metadata, data, trademarks or publications. This document identifies
sources; it does not relicense third-party material or certify permission for a particular use.

## Public discovery metadata

`backend/src/macro_research_agent/knowledge/source_index_lite.sqlite3` contains provider-derived
catalog identities collected on **2026-09-12 UTC**. Attribution belongs to the providers below.
For every dataset, the database retains the original provider and dataset code/title; each
indicator retains its provider, code and label. The `providers` table records the exact access
timestamp, catalog URL, snapshot version and source checksum.

The public projection is modified for discovery: dataset descriptions/HTML/contact text are
omitted, repeated indicator sets are deduplicated, executable admission flags are supplied by
this application, and full-text indexes are derived. It is not an official catalog mirror or a
current availability claim. It contains no observation series, full provider responses, uploaded
files or research-session records. The complete dimension database and raw harvests are excluded.

| Source and original catalog | Provider terms |
| --- | --- |
| International Monetary Fund, [IMF Data catalog](https://data.imf.org/en/Resource-Pages/IMF-API) | [Copyright and statistical-data usage](https://www.imf.org/en/About/copyright-and-terms) |
| World Bank, [Indicators sources](https://api.worldbank.org/v2/source?format=json) | [Terms and conditions, including datasets](https://www.worldbank.org/ext/en/legal/terms-conditions) |
| Organisation for Economic Co-operation and Development, [data API](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html) | [Terms and conditions](https://www.oecd.org/en/about/terms-conditions.html) |
| Eurostat, [catalog API](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-getting-started/catalogue-api) | [Copyright and reuse notice](https://ec.europa.eu/eurostat/help/copyright-notice) |
| Asian Development Bank, [Key Indicators Database API](https://kidb.adb.org/api) | [KIDB terms](https://kidb.adb.org/terms) |
| European Central Bank, [Data Portal API](https://data.ecb.europa.eu/help/api/data) | [Disclaimer and copyright](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html) |
| Bank for International Settlements, [statistics API](https://stats.bis.org/api-doc/v2/) | [Statistics terms](https://www.bis.org/terms_statistics.htm) |
| United Nations Statistics Division, [SDG API](https://unstats.un.org/SDGAPI/swagger/index.html) | [United Nations terms](https://www.un.org/en/about-us/terms-of-use), plus applicable series-source terms |

Keep the dataset/indicator identity, source attribution, access date, modification statement and
applicable terms with any extract. Check dataset-specific and third-party-source restrictions;
public API access alone does not establish unrestricted reuse or redistribution. Provider names
identify sources only. This independent project is not affiliated with, approved by or endorsed by
these providers, and it does not license their names or logos.

## Acquired research data

Observations are acquired only when a local user runs a registered connector or supplies a file;
they are not part of the public source distribution. The operator is responsible for checking
source rights, attribution, permitted model disclosure and onward sharing. Transformations must
not be represented as original provider statistics. Publications and cited methodological context
have their own rights and are not automatically covered by a dataset's terms.

## Software dependencies and assets

Python dependency ranges are in [pyproject.toml](pyproject.toml); the actual installed environment
determines resolved versions. Frontend versions are recorded in
[package-lock.json](frontend/package-lock.json). Their packages retain the license/copyright
notices supplied by their maintainers. Install-time access does not merge those licenses into a
license for this application. Generated distributions must preserve applicable notices.

The interface uses locally stored project assets and system fonts, not a bundled institutional
logo or a redistributed commercial font family. The
[academic publication placeholder](guidelines/academic-publication-placeholder-v1.md) is an
independent working rubric inspired by cited publication guidance, not an official journal
template, endorsement or submission-compliance certificate.
