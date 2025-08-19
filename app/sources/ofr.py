from __future__ import annotations

from datetime import datetime, UTC
from typing import Dict, Any, List, Optional
import csv
import io

import httpx


async def fetch_liquidity_stress_csv(url: str, *, timeout_seconds: int = 30) -> str:
	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		r = await client.get(url)
		r.raise_for_status()
		return r.text


def parse_liquidity_stress_csv(csv_text: str) -> List[Dict[str, Any]]:
	rows: List[Dict[str, Any]] = []
	reader = csv.DictReader(io.StringIO(csv_text))

	def norm(s: str) -> str:
		return " ".join(s.strip().lower().replace("_", " ").split())

	for raw in reader:
		if not raw:
			continue
		# Date
		date_key: Optional[str] = None
		for k in raw.keys():
			if norm(k) == "date" or norm(k) == "observation date":
				date_key = k
				break
		if not date_key or not raw.get(date_key):
			continue
		obs_date = None
		for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
			try:
				obs_date = datetime.strptime(raw[date_key].strip(), fmt).date()
				break
			except Exception:
				pass
		if obs_date is None:
			continue
		# Value: strictly use the composite column "OFR FSI"
		value_key: Optional[str] = None
		for k in raw.keys():
			if norm(k) == "ofr fsi":
				value_key = k
				break
		if value_key is None:
			continue
		val_str = raw.get(value_key)
		if val_str in (None, "", "."):
			continue
		try:
			val_num = float(str(val_str).replace(",", ""))
		except Exception:
			continue
		rows.append(
			{
				"observation_date": obs_date,
				"vintage_date": None,
				"publication_date": None,
				"fetched_at": datetime.now(UTC),
				"value_numeric": val_num,
			}
		)
	return rows



