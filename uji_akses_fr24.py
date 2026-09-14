"""Uji kelayakan akses FR24 dari GitHub Actions (bukan dari laptop).

Tujuan: menjawab apakah scraping anonim masih mungkin setelah FR24 merombak
halaman data (Sep 2026). Skrip ini HANYA membaca dan melapor - tidak menyimpan
apa pun. Sengaja dijalankan di runner GitHub supaya IP pribadi tidak terpakai.

Yang diperiksa:
  1. Papan saat ini  - berapa baris terbaca, rentang jam, sebaran status
  2. "Earlier flights" - apakah masih 403 seperti saat diuji dari laptop
  3. XHR ?date=&page= - apakah bisa menargetkan tanggal tertentu
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

WIB = timezone(timedelta(hours=7))
IATA = "cgk"

EKSTRAK = r"""() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href*="/data/flights/"]')) {
    let row = a;
    for (let i=0;i<8 && row.parentElement;i++){ row = row.parentElement;
      if ((row.textContent||'').length > 60) break; }
    const t = (row.textContent||'').replace(/\s+/g,' ').trim();
    const jam = t.match(/\b\d{1,2}:\d{2}\s*(?:AM|PM)\b/g) || [];
    const st  = t.match(/\b(Landed|Departed|Estimated|Scheduled|Canceled|Delayed|Diverted|Unknown)\b/i);
    if (jam[0]) out.push({jadwal: jam[0], status: st ? st[0] : ''});
  }
  return out;
}"""


def ke_jam(s):
    try:
        return datetime.strptime(s.replace(" ", ""), "%I:%M%p").time()
    except Exception:
        return None


def main():
    print("=" * 62)
    print(f"  Uji akses FR24 dari GitHub Actions")
    print(f"  Waktu: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}")
    print("=" * 62)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(
            locale="en-US", timezone_id="Asia/Jakarta",
            viewport={"width": 1400, "height": 900},
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"))
        pg = ctx.new_page()

        kode_xhr = []
        pg.on("response", lambda r: kode_xhr.append(r.status)
              if f"/data/airports/{IATA}/arrivals?" in r.url else None)

        url = f"https://www.flightradar24.com/data/airports/{IATA}/arrivals"
        resp = pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"\n[1] Papan saat ini — HTTP {resp.status if resp else '?'}")
        try:
            pg.wait_for_selector('a[href*="/data/flights/"]', timeout=30000)
        except Exception:
            print("    (selector tak muncul dalam 30 dtk)")
        pg.wait_for_timeout(5000)

        rows = pg.evaluate(EKSTRAK)
        print(f"    Baris terbaca : {len(rows)}")
        if rows:
            jam = sorted(j for j in (ke_jam(r["jadwal"]) for r in rows) if j)
            if jam:
                print(f"    Rentang jadwal: {jam[0]:%H:%M} -> {jam[-1]:%H:%M}")
            print(f"    Status        : {dict(Counter(r['status'] for r in rows).most_common(6))}")
            final = sum(1 for r in rows
                        if r["status"] in ("Landed", "Departed", "Canceled", "Diverted"))
            print(f"    Sudah final   : {final}/{len(rows)} ({100*final/len(rows):.0f}%)")

        # [2] tombol Earlier flights
        print("\n[2] Tombol 'Earlier flights'")
        kode_xhr.clear()
        ada = pg.evaluate("""() => { const b=[...document.querySelectorAll('button,a')]
            .find(e=>/earlier flight|load earlier|load more|show more/i.test(e.innerText||''));
            if (b) { b.scrollIntoView({block:'center'}); b.click(); return true; } return false; }""")
        print(f"    Tombol ada    : {ada}")
        if ada:
            pg.wait_for_timeout(6000)
            setelah = pg.evaluate("() => document.querySelectorAll('a[href*=\"/data/flights/\"]').length")
            print(f"    HTTP XHR      : {kode_xhr or '(tak terekam)'}")
            print(f"    Baris setelah : {setelah}")

        # [3] XHR langsung dengan parameter tanggal
        print("\n[3] XHR ?date=&page= (target tanggal tertentu)")
        ts = int((datetime.now(WIB) - timedelta(days=1))
                 .replace(hour=12, minute=0, second=0, microsecond=0).timestamp())
        hasil = pg.evaluate("""async ({iata, ts}) => {
            const r = await fetch(`/data/airports/${iata}/arrivals?date=${ts}&page=-1`,
                                  {headers:{'x-requested-with':'XMLHttpRequest'}});
            if (!r.ok) return {http:r.status, baris:0};
            const d = new DOMParser().parseFromString(await r.text(),'text/html');
            return {http:200, baris:d.querySelectorAll('a[href*="/data/flights/"]').length};
        }""", {"iata": IATA, "ts": ts})
        print(f"    HTTP          : {hasil['http']}")
        print(f"    Baris         : {hasil['baris']}")

        b.close()

    print("\n" + "=" * 62)
    print("  Selesai. Tidak ada data yang disimpan.")


if __name__ == "__main__":
    main()
