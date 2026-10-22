# 真实 query 双人标注比对

共同标注 100 条，完全一致 77 条（77.0%）。

| 分歧字段 | 次数 |
| --- | ---: |
| location_keywords | 10 |
| soft_preferences | 9 |
| layout_options | 5 |
| commute_destination | 4 |
| intent | 3 |
| bills_included | 2 |
| max_rent | 2 |
| let_type | 1 |
| available_from | 1 |

## 分歧明细

- `REAL-013` "I'm looking for a studio flat for one Person. Maximum 10 miles from Chiswick. £1050 with all bills."
  - bills_included: gpt=true claude=null
  - soft_preferences: gpt=["Maximum 10 miles from Chiswick"] claude=[]
- `REAL-031` "I'm looking to rent a one bed flat by myself, with my budget 1850 pounds per month - am I cooked? I'm currently living in Chiswick but open to other areas of London that have a safe and nice feel (ideally I'd like to reduce my commute to Bank, but this is negotiable)."
  - location_keywords: gpt=["London"] claude=[]
- `REAL-032` 'So currently I’m looking for a 2 bedroom flat in London and the search was going well up to a point we found some that would suit us but they were gone in an instant and ever since then it’s been nearly impossible to find one (Our budget is max 1700 a month). We are looking for apartments in nice and safe neighborhoods in within north east and west especially or even central.'
  - location_keywords: gpt=["London", "north", "east", "west", "central"] claude=["London"]
- `REAL-034` "I'll be moving to London in mid July and am really very confused as to which area is quite safe for a single person to rent a one bedroom flat. The budget is a maximum 1500 pcm with a council tax in the range of 200 GBP. Can anyone please suggest safe and good areas to rent a single bed flat which will be maximum an hour from Holborn High station?"
  - location_keywords: gpt=["London", "Holborn High station"] claude=["London"]
  - soft_preferences: gpt=["quite safe", "safe and good areas", "maximum an hour from Holborn High station"] claude=[]
- `REAL-039` 'My office is in Oxford Street in Central London and I’m looking for a 1 bed flat for me and my partner. Our budget is £1500 for rent. Which areas in London should I look into.'
  - location_keywords: gpt=["London"] claude=[]
- `REAL-040` 'Family of 3 + dog, reasonably high budget, need to move by 30 April, want NW-ish (Kilburn/Kentish Town/Camden-ish) and a reliable, well-managed flat (new build/concierge/good maintenance) rather than "character".'
  - location_keywords: gpt=["NW-ish", "Kilburn", "Kentish Town", "Camden-ish"] claude=["NW", "Kilburn", "Kentish Town", "Camden"]
- `REAL-042` "As the title says, I'm trying to figure out the best way to find a decent flat in London as an immigrant, and in a pretty short time period."
  - intent: gpt=Search claude=Chitchat
  - location_keywords: gpt=["London"] claude=[]
  - layout_options: gpt=[{"bedrooms": null, "bathrooms": null, "property_type": "flat"}] claude=[]
  - soft_preferences: gpt=["decent"] claude=[]
- `REAL-045` 'I’m looking for a 2BR or 1 bed with an office, under £2500 before bills. I’ve done a lot of searching and have found nice flats in Walthamstow, Leytonstone, Willesden, Brockley, Forest Gate, and Haringey so would love to hear thoughts on those, but open to anything!'
  - layout_options: gpt=[{"bedrooms": 2, "bathrooms": null, "property_type": "flat"}, {"bedrooms": 1, "bathrooms": null, "property_type": "flat"}] claude=[{"bedrooms": 2, "bathrooms": null, "property_type": null}, {"bedrooms": 1, "bathrooms": null, "property_type": null}]
- `REAL-046` "Hey, I'm a student moving to London mid-August and I am looking for a 1B flat in Zone 1, ideally close to my uni (near Regent's Park) for at least 1 year."
  - location_keywords: gpt=["London", "Zone 1"] claude=["Zone 1"]
  - commute_destination: gpt=null claude="Regent's Park"
- `REAL-049` "Hey, I'm currently a student living in the Netherlands, I'm moving to London for work in August of 2026 right after exams, so I'm unable to visit there to do viewings before moving. I'm looking for something with a good connection (30 min travel-time tops) to the financial district, I'm prepared to spend 2-5k gbp pcm on rent, though I would prefer to keep it around 3.5k."
  - commute_destination: gpt=null claude="financial district"
- `REAL-054` 'My partner and I are moving from Manchester to London in the next month or two.\n\nHis office is near Liverpool Street and I’ll be working around Cannon Street, so we’re looking for a 1BR with a commute of not than an hour via public transport.\n\nOur budget is around 1400 to 1600 a month, but we’d love to keep costs on the down low given there will be more bills to pay.'
  - soft_preferences: gpt=["a commute of not than an hour via public transport"] claude=[]
- `REAL-057` 'I currently live in NW London and want to move to W London like shepherds bush, Acton or Ealing (near the lizzy line)\n\nI have been browsing some really nice spacious 3 bedroom terrace houses with a garden and I would so love that as an option of a place to live.'
  - location_keywords: gpt=["W London", "shepherds bush", "Acton", "Ealing", "lizzy line"] claude=["W London", "shepherds bush", "Acton", "Ealing"]
  - layout_options: gpt=[] claude=[{"bedrooms": 3, "bathrooms": null, "property_type": null}]
- `REAL-058` "I used to live in London and return regularly for short stays. I'm looking for someone who travels frequently and would like a reliable person to stay in and look after their flat while they're away.\n\nIdeally North London - Kentish Town, Tufnell Park, Highgate, Archway, Crouch End, East Finchley or nearby - but I'm flexible."
  - intent: gpt=Search claude=Chitchat
  - layout_options: gpt=[{"bedrooms": null, "bathrooms": null, "property_type": "flat"}] claude=[]
  - let_type: gpt="short term" claude=null
  - soft_preferences: gpt=["North London - Kentish Town, Tufnell Park, Highgate, Archway, Crouch End, East Finchley or nearby"] claude=[]
- `REAL-060` 'Me and my partner are looking to rent somewhere within 50 min commuting distance to central London.\n\nWe can technically afford more than £1500/month, but I had hoped to save more of our monthly income for putting money aside for a deposit.\nHowever, after spending quite a lot of time on RightMove / OpenRent it seems like our options are quite limited, especially since we have cats.'
  - soft_preferences: gpt=["within 50 min commuting distance to central London"] claude=[]
- `REAL-064` 'We are looking for a 1B1B for about £2000, ideally want to be on Central/ Jubilee line, Zone 1 or 2.\nOkay with a <30 min commute to Mayfair / central London by Tube.'
  - commute_destination: gpt="Mayfair / central London" claude="Mayfair"
- `REAL-065` 'Campus is basically within Trafalgar Square and I am willing to look around 20 ish mins on public transport to get there. Ideally a room for around than 750-800 pounds PCM with others that is ideally furnished.'
  - max_rent: gpt=null claude={"value": 800, "period": "pcm"}
- `REAL-068` 'What’s your experience trying to rent in London? I’ve just started looking at flats to rent with my partner and a flat that went up on Friday has already had multiple offers and been taken off the market.'
  - intent: gpt=Search claude=Chitchat
  - location_keywords: gpt=["London"] claude=[]
  - layout_options: gpt=[{"bedrooms": null, "bathrooms": null, "property_type": "flat"}] claude=[]
- `REAL-070` 'Let’s also include the cost of the commute in the calculation. Ignoring all other factors (again within reason, I’m not talking about living in a crackhouse without electricity), where would it be cheapest to rent a studio flat and commute in to central London? Let’s say King’s Cross, to be precise.'
  - commute_destination: gpt="King’s Cross" claude="King's Cross"
- `REAL-071` "We're looking for a four bedroom place for a maximum of 3,400 pcm including bills."
  - bills_included: gpt=true claude=null
- `REAL-073` "I'm looking for a single studio not too far away from Imperial College's main campus, possibly under 200£ per week."
  - location_keywords: gpt=["Imperial College's main campus"] claude=["Imperial College"]
  - max_rent: gpt=null claude={"value": 200, "period": "pw"}
  - soft_preferences: gpt=["under 200£ per week"] claude=[]
- `REAL-075` 'We are looking to rent a 2 or 3 bedrooms with good connections to Kings cross where we work.'
  - soft_preferences: gpt=["good connections to Kings cross"] claude=[]
- `REAL-089` 'Im looking for 1 bed flat that accepts dss for a mother and a newborn by 1st of may 2025 thanks'
  - available_from: gpt=null claude="2025-05"
- `REAL-099` 'We’re looking for a 2 bedroom whole flat in South West London.'
  - soft_preferences: gpt=[] claude=["whole flat"]
