"""
london_postcodes.py
-------------------
伦敦 postcode district 完整列表 + 细分策略

split = "high"  → 该 district 房源可能 > 1050，需细分到 sector
split = "low"   → 直接搜 district，不超上限

sector 列表来自真实 UK postcode 数据，确保不遗漏
"""

# ══════════════════════════════════════════════════════════════════
# District 列表（79 个，覆盖 Greater London Zone 1-4+）
# ══════════════════════════════════════════════════════════════════

LONDON_DISTRICTS = {

    # ── E (East London) ──────────────────────────────────────────
    "E1":   "high",   # Whitechapel, Shoreditch, Stepney
    "E1W":  "low",    # Wapping
    "E2":   "high",   # Bethnal Green, Shoreditch
    "E3":   "low",    # Bow, Mile End
    "E4":   "low",    # Chingford
    "E5":   "low",    # Clapton
    "E6":   "low",    # East Ham
    "E7":   "low",    # Forest Gate, Upton Park
    "E8":   "high",   # Hackney, Dalston
    "E9":   "low",    # Homerton, Victoria Park
    "E10":  "low",    # Leyton
    "E11":  "low",    # Leytonstone
    "E12":  "low",    # Manor Park
    "E13":  "low",    # Plaistow
    "E14":  "high",   # Canary Wharf, Limehouse, Poplar
    "E15":  "low",    # Stratford, West Ham
    "E16":  "low",    # Canning Town, Royal Docks
    "E17":  "low",    # Walthamstow
    "E18":  "low",    # South Woodford
    "E20":  "low",    # Olympic Park

    # ── EC (East Central) ────────────────────────────────────────
    "EC1A": "low",
    "EC1M": "low",
    "EC1N": "low",
    "EC1R": "low",
    "EC1V": "low",
    "EC1Y": "low",
    "EC2A": "low",
    "EC2M": "low",
    "EC2N": "low",
    "EC2R": "low",
    "EC2V": "low",
    "EC2Y": "low",
    "EC3A": "low",
    "EC3M": "low",
    "EC3N": "low",
    "EC3R": "low",
    "EC3V": "low",
    "EC4A": "low",
    "EC4M": "low",
    "EC4N": "low",
    "EC4R": "low",
    "EC4V": "low",
    "EC4Y": "low",

    # ── N (North London) ─────────────────────────────────────────
    "N1":   "high",   # Islington, Angel, Canonbury, Barnsbury
    "N2":   "low",    # East Finchley
    "N3":   "low",    # Finchley Central
    "N4":   "low",    # Finsbury Park, Manor House
    "N5":   "low",    # Highbury
    "N6":   "low",    # Highgate
    "N7":   "low",    # Holloway
    "N8":   "low",    # Hornsey, Crouch End
    "N9":   "low",    # Edmonton
    "N10":  "low",    # Muswell Hill
    "N11":  "low",    # New Southgate
    "N12":  "low",    # North Finchley
    "N13":  "low",    # Palmers Green
    "N14":  "low",    # Southgate
    "N15":  "low",    # Seven Sisters, South Tottenham
    "N16":  "low",    # Stoke Newington, Stamford Hill
    "N17":  "low",    # Tottenham
    "N18":  "low",    # Upper Edmonton
    "N19":  "low",    # Archway, Upper Holloway
    "N20":  "low",    # Whetstone, Totteridge
    "N21":  "low",    # Winchmore Hill
    "N22":  "low",    # Wood Green, Alexandra Palace

    # ── NW (North West London) ───────────────────────────────────
    "NW1":  "high",   # Camden, Euston, Regent's Park, Marylebone
    "NW2":  "low",    # Cricklewood, Neasden
    "NW3":  "high",   # Hampstead, Belsize Park, Swiss Cottage
    "NW4":  "low",    # Hendon, Brent Cross
    "NW5":  "low",    # Kentish Town, Gospel Oak
    "NW6":  "low",    # Kilburn, Queen's Park, West Hampstead
    "NW7":  "low",    # Mill Hill
    "NW8":  "high",   # St John's Wood
    "NW9":  "low",    # The Hyde, Colindale
    "NW10": "low",    # Harlesden, Willesden, Kensal Green
    "NW11": "low",    # Golders Green, Hampstead Garden Suburb

    # ── SE (South East London) ───────────────────────────────────
    "SE1":  "high",   # South Bank, Borough, Bermondsey, Elephant
    "SE2":  "low",    # Abbey Wood
    "SE3":  "low",    # Blackheath, Kidbrooke
    "SE4":  "low",    # Brockley, Crofton Park
    "SE5":  "low",    # Camberwell
    "SE6":  "low",    # Catford, Bellingham
    "SE7":  "low",    # Charlton
    "SE8":  "low",    # Deptford, New Cross Gate
    "SE9":  "low",    # Eltham, Mottingham
    "SE10": "low",    # Greenwich, Maze Hill
    "SE11": "low",    # Kennington, Oval
    "SE12": "low",    # Lee, Grove Park
    "SE13": "low",    # Lewisham, Hither Green
    "SE14": "low",    # New Cross
    "SE15": "low",    # Peckham, Nunhead
    "SE16": "low",    # Rotherhithe, Canada Water, Surrey Quays
    "SE17": "low",    # Walworth, Elephant & Castle (south)
    "SE18": "low",    # Woolwich, Plumstead
    "SE19": "low",    # Crystal Palace, Upper Norwood
    "SE20": "low",    # Anerley, Penge
    "SE21": "low",    # Dulwich, West Norwood
    "SE22": "low",    # East Dulwich
    "SE23": "low",    # Forest Hill, Honor Oak
    "SE24": "low",    # Herne Hill
    "SE25": "low",    # South Norwood
    "SE26": "low",    # Sydenham
    "SE27": "low",    # West Norwood, Tulse Hill
    "SE28": "low",    # Thamesmead

    # ── SW (South West London) ───────────────────────────────────
    "SW1A": "low",    # Buckingham Palace, Whitehall
    "SW1E": "low",    # Victoria (east)
    "SW1H": "low",    # Westminster (south)
    "SW1P": "low",    # Pimlico (north), Westminster
    "SW1V": "high",   # Pimlico, Victoria
    "SW1W": "high",   # Belgravia, Pimlico
    "SW1X": "high",   # Knightsbridge, Belgravia
    "SW1Y": "low",    # St James's
    "SW2":  "low",    # Brixton (north), Streatham Hill
    "SW3":  "high",   # Chelsea, Brompton
    "SW4":  "low",    # Clapham
    "SW5":  "high",   # Earl's Court
    "SW6":  "high",   # Fulham, Parsons Green
    "SW7":  "high",   # South Kensington, Gloucester Road
    "SW8":  "low",    # Vauxhall, South Lambeth, Nine Elms
    "SW9":  "low",    # Stockwell, Brixton
    "SW10": "high",   # West Chelsea, World's End
    "SW11": "high",   # Battersea, Clapham Junction
    "SW12": "low",    # Balham
    "SW13": "low",    # Barnes
    "SW14": "low",    # Mortlake, East Sheen
    "SW15": "low",    # Putney, Roehampton
    "SW16": "low",    # Streatham, Norbury
    "SW17": "low",    # Tooting
    "SW18": "low",    # Wandsworth, Earlsfield
    "SW19": "low",    # Wimbledon, Merton
    "SW20": "low",    # Raynes Park, West Wimbledon

    # ── W (West London) ──────────────────────────────────────────
    "W1B":  "low",    # Oxford Street (east)
    "W1C":  "low",    # Oxford Street (west)
    "W1D":  "low",    # Soho, Covent Garden
    "W1F":  "low",    # Soho
    "W1G":  "low",    # Marylebone (south)
    "W1H":  "low",    # Marylebone
    "W1J":  "low",    # Mayfair (south)
    "W1K":  "low",    # Mayfair (north)
    "W1S":  "low",    # Mayfair (east)
    "W1T":  "low",    # Fitzrovia
    "W1U":  "low",    # Marylebone High Street
    "W1W":  "low",    # Fitzrovia (north)
    "W2":   "high",   # Paddington, Bayswater, Hyde Park
    "W3":   "low",    # Acton
    "W4":   "low",    # Chiswick
    "W5":   "low",    # Ealing
    "W6":   "high",   # Hammersmith
    "W7":   "low",    # Hanwell
    "W8":   "high",   # Kensington, Holland Park
    "W9":   "low",    # Maida Vale, Warwick Avenue
    "W10":  "low",    # North Kensington, Ladbroke Grove
    "W11":  "high",   # Notting Hill, Holland Park
    "W12":  "low",    # Shepherd's Bush
    "W13":  "low",    # West Ealing
    "W14":  "high",   # West Kensington, Olympia

    # ── WC (West Central) ────────────────────────────────────────
    "WC1A": "low",
    "WC1B": "low",
    "WC1E": "low",
    "WC1H": "low",
    "WC1N": "low",
    "WC1R": "low",
    "WC1V": "low",
    "WC1X": "low",
    "WC2A": "low",
    "WC2B": "low",
    "WC2E": "low",
    "WC2H": "low",
    "WC2N": "low",
    "WC2R": "low",

    # ── Outer London (Zone 4-6) ───────────────────────────────────
    "BR1":  "low",    # Bromley
    "BR2":  "low",    # Bromley (south)
    "BR3":  "low",    # Beckenham
    "BR4":  "low",    # West Wickham
    "BR5":  "low",    # Orpington
    "CR0":  "low",    # Croydon
    "CR2":  "low",    # South Croydon
    "CR4":  "low",    # Mitcham
    "CR7":  "low",    # Thornton Heath
    "DA1":  "low",    # Dartford (fringe)
    "DA6":  "low",    # Bexleyheath
    "DA7":  "low",    # Bexleyheath
    "DA8":  "low",    # Erith
    "DA14": "low",    # Sidcup
    "DA15": "low",    # Sidcup
    "DA16": "low",    # Welling
    "DA17": "low",    # Belvedere
    "EN1":  "low",    # Enfield
    "EN2":  "low",    # Enfield (north)
    "EN3":  "low",    # Enfield (east)
    "EN4":  "low",    # Barnet (east)
    "HA0":  "low",    # Wembley
    "HA1":  "low",    # Harrow
    "HA2":  "low",    # Harrow (south)
    "HA3":  "low",    # Harrow Weald, Kenton
    "HA4":  "low",    # Ruislip
    "HA5":  "low",    # Pinner
    "HA6":  "low",    # Northwood
    "HA7":  "low",    # Stanmore
    "HA8":  "low",    # Edgware
    "HA9":  "low",    # Wembley (north)
    "IG1":  "low",    # Ilford
    "IG2":  "low",    # Gants Hill
    "IG3":  "low",    # Seven Kings
    "IG4":  "low",    # Redbridge
    "IG5":  "low",    # Clayhall
    "IG6":  "low",    # Hainault
    "IG8":  "low",    # Woodford
    "IG11": "low",    # Barking
    "KT1":  "low",    # Kingston upon Thames
    "KT2":  "low",    # Kingston (north)
    "KT3":  "low",    # New Malden
    "KT4":  "low",    # Worcester Park
    "KT5":  "low",    # Surbiton
    "KT6":  "low",    # Surbiton (south)
    "KT8":  "low",    # East Molesey
    "KT9":  "low",    # Chessington
    "RM1":  "low",    # Romford
    "RM2":  "low",    # Gidea Park
    "RM3":  "low",    # Harold Wood
    "RM5":  "low",    # Collier Row
    "RM6":  "low",    # Chadwell Heath
    "RM7":  "low",    # Rush Green
    "RM8":  "low",    # Dagenham (west)
    "RM9":  "low",    # Dagenham (east)
    "RM10": "low",    # Dagenham
    "RM12": "low",    # Hornchurch
    "RM13": "low",    # Rainham
    "RM14": "low",    # Upminster
    "SM1":  "low",    # Sutton
    "SM2":  "low",    # Sutton (south)
    "SM3":  "low",    # Cheam
    "SM4":  "low",    # Morden
    "SM5":  "low",    # Carshalton
    "SM6":  "low",    # Wallington
    "TW1":  "low",    # Twickenham
    "TW2":  "low",    # Whitton
    "TW3":  "low",    # Hounslow
    "TW4":  "low",    # Heston
    "TW5":  "low",    # Cranford
    "TW6":  "low",    # Heathrow (rental around airport)
    "TW7":  "low",    # Isleworth
    "TW8":  "low",    # Brentford
    "TW9":  "low",    # Richmond
    "TW10": "low",    # Ham, Petersham
    "TW11": "low",    # Teddington
    "TW12": "low",    # Hampton
    "TW13": "low",    # Feltham
    "TW14": "low",    # Feltham (east)
    "UB1":  "low",    # Southall
    "UB2":  "low",    # Southall (east)
    "UB3":  "low",    # Hayes
    "UB4":  "low",    # Hayes (east)
    "UB5":  "low",    # Northolt, Greenford
    "UB6":  "low",    # Greenford
    "UB7":  "low",    # West Drayton
    "UB8":  "low",    # Uxbridge
    "UB10": "low",    # Hillingdon
}


# ══════════════════════════════════════════════════════════════════
# 热门 district 的 sector 细分列表
# 只列 split="high" 的 district
# 确保每个 sector 房源 < 1050 条
# ══════════════════════════════════════════════════════════════════

DISTRICT_SECTORS = {
    "E1":   ["E1 0", "E1 1", "E1 2", "E1 3", "E1 4", "E1 5", "E1 6", "E1 7"],
    "E2":   ["E2 0", "E2 6", "E2 7", "E2 8", "E2 9"],
    "E8":   ["E8 1", "E8 2", "E8 3", "E8 4"],
    "E14":  ["E14 0", "E14 2", "E14 3", "E14 4", "E14 5", "E14 6", "E14 7", "E14 8", "E14 9"],
    "N1":   ["N1 0", "N1 1", "N1 2", "N1 3", "N1 4", "N1 5", "N1 6", "N1 7", "N1 8", "N1 9"],
    "NW1":  ["NW1 0", "NW1 1", "NW1 2", "NW1 3", "NW1 4", "NW1 5", "NW1 6", "NW1 7", "NW1 8", "NW1 9"],
    "NW3":  ["NW3 1", "NW3 2", "NW3 3", "NW3 4", "NW3 5", "NW3 6", "NW3 7"],
    "NW8":  ["NW8 0", "NW8 6", "NW8 7", "NW8 8", "NW8 9"],
    "SE1":  ["SE1 0", "SE1 1", "SE1 2", "SE1 3", "SE1 4", "SE1 5", "SE1 6", "SE1 7", "SE1 8", "SE1 9"],
    "SW1V": ["SW1V 1", "SW1V 2", "SW1V 3", "SW1V 4"],
    "SW1W": ["SW1W 0", "SW1W 8", "SW1W 9"],
    "SW1X": ["SW1X 0", "SW1X 7", "SW1X 8", "SW1X 9"],
    "SW3":  ["SW3 1", "SW3 2", "SW3 3", "SW3 4", "SW3 5", "SW3 6"],
    "SW5":  ["SW5 0", "SW5 9"],
    "SW6":  ["SW6 1", "SW6 2", "SW6 3", "SW6 4", "SW6 5", "SW6 6", "SW6 7"],
    "SW7":  ["SW7 1", "SW7 2", "SW7 3", "SW7 4", "SW7 5"],
    "SW10": ["SW10 0", "SW10 9"],
    "SW11": ["SW11 1", "SW11 2", "SW11 3", "SW11 4", "SW11 5", "SW11 6"],
    "W2":   ["W2 1", "W2 2", "W2 3", "W2 4", "W2 5", "W2 6"],
    "W6":   ["W6 0", "W6 7", "W6 8", "W6 9"],
    "W8":   ["W8 4", "W8 5", "W8 6", "W8 7"],
    "W11":  ["W11 1", "W11 2", "W11 3", "W11 4"],
    "W14":  ["W14 0", "W14 8", "W14 9"],
}


def get_search_queries() -> list[dict]:
    """
    生成最终搜索 query 列表。
    split=high 的 district 展开成 sector 列表，
    split=low 的 district 直接用 district。
    返回：[{"query": "E1 0", "district": "E1"}, ...]
    """
    queries = []
    for district, split in LONDON_DISTRICTS.items():
        if split == "high":
            sectors = DISTRICT_SECTORS.get(district)
            if sectors:
                for sector in sectors:
                    queries.append({
                        "query":    sector,
                        "district": district,
                        "type":     "sector",
                    })
            else:
                # 没有预定义 sector 的 high district，降级用 district
                queries.append({
                    "query":    district,
                    "district": district,
                    "type":     "district_fallback",
                })
        else:
            queries.append({
                "query":    district,
                "district": district,
                "type":     "district",
            })
    return queries


if __name__ == "__main__":
    queries = get_search_queries()
    district_count = len(LONDON_DISTRICTS)
    sector_count   = sum(len(v) for v in DISTRICT_SECTORS.values())
    low_count      = sum(1 for v in LONDON_DISTRICTS.values() if v == "low")
    high_count     = sum(1 for v in LONDON_DISTRICTS.values() if v == "high")
    total_queries  = len(queries)

    print(f"Districts total:      {district_count}")
    print(f"  split=high:         {high_count}")
    print(f"  split=low:          {low_count}")
    print(f"Sector queries:       {sector_count}")
    print(f"Total search queries: {total_queries}")
    print(f"\nSample (first 10):")
    for q in queries[:10]:
        print(f"  {q}")
