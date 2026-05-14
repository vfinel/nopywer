# Cable cost fits for the optimiser

Nopywer's optimiser currently uses dimensionless cable tier costs:

| Repo class | Phases | Connector rating | Section |
|------------|--------|------------------|---------|
| `Cable16A` | 1P     | 16 A             | 2.5 mm2 |
| `Cable32A` | 3P     | 32 A             | 6 mm2   |
| `Cable63A` | 3P     | 63 A             | 16 mm2  |
| `Cable125A`| 3P     | 125 A            | 35 mm2  |

Those classes are used as a planning abstraction, but the optimiser's
objective is meant to represent a real-world purchasing cost. A useful
market model is therefore:

```text
finished_cable_price_eur = a + b * length_m
```

where the price is for a complete extension lead: flexible rubber cable,
plug, socket/coupler, assembly, testing, VAT where listed, and shop
margin. Shipping is excluded.

This is deliberately **not** a raw-cable-plus-connectors bill of
materials. A 100 m cable with ends attached is a different product from
100 m of loose cable and two connector parts; finished-lead listings are
the better evidence for the optimiser.

## Recommended fits

Ordinary least squares fits over complete-lead listings give:

| Repo class | Market equivalent | Fitted price model |
|------------|-------------------|--------------------|
| `Cable16A` | CEE 230 V 16 A, H07RN-F 3G2.5 | `24.57 + 2.22 * length_m` |
| `Cable32A` | CEE 400 V 32 A, H07RN-F 5G6   | `59.32 + 5.48 * length_m` |
| `Cable63A` | CEE 400 V 63 A, H07RN-F 5G16  | `166.22 + 20.87 * length_m` |
| `Cable125A`| CEE 400 V 125 A, H07RN-F 5G35 | `149.00 + 50.00 * length_m` |

The intercept is not just connector cost. It includes the fixed part of
retail pricing: termination labour, testing, SKU handling, minimum
margin, and short-length pricing effects. The slope is the observed
extra cost per added metre in a finished product line.

## Source observations

### `Cable16A`: 230 V / 16 A / H07RN-F 3G2.5

Source: ENECEN, "CEE-Verlaengerungskabel 230V/16A IP44 Gummi
H07RN-F 3x2,5 mm2 mit ST/KU 3-polig".

<https://www.enecen.com/CEE-Verlaengerungskabel-230V-16A-IP44-Gummi-H07RN-F-3x25-mm-mit-ST-KU-3-polig>

| Length | Listed price |
|-------:|-------------:|
| 5 m    | 35.68 EUR |
| 10 m   | 46.80 EUR |
| 25 m   | 80.13 EUR |
| 40 m   | 113.48 EUR |
| 50 m   | 135.70 EUR |

Fit:

```text
price_eur = 24.57 + 2.22 * length_m
```

### `Cable32A`: 400 V / 32 A / H07RN-F 5G6

Source: Lecos-Elektronik, "CEE 32A Starkstrom Verlaengerungskabel
5x6mm2 H07RN-F".

<https://lecos-elektronik.de/starkstrom-verlaengerungskabel/cee-32a-5x6mm2-h07rn-f/>

| Length | Listed price |
|-------:|-------------:|
| 10 m   | 115.90 EUR |
| 15 m   | 144.90 EUR |
| 25 m   | 189.00 EUR |
| 50 m   | 335.90 EUR |

Fit:

```text
price_eur = 59.32 + 5.48 * length_m
```

### `Cable63A`: 400 V / 63 A / H07RN-F 5G16

Source: Lecos-Elektronik, "CEE 63A Starkstrom Verlaengerungskabel
5x16mm2 H07RN-F".

<https://lecos-elektronik.de/starkstrom-verlaengerungskabel/cee-63a-5x16mm2-h07rn-f/>

| Length | Listed price used |
|-------:|------------------:|
| 10 m   | 339.00 EUR |
| 15 m   | 499.00 EUR |
| 20 m   | 599.00 EUR |
| 25 m   | 699.00 EUR |
| 50 m   | 1199.00 EUR |

Fit:

```text
price_eur = 166.22 + 20.87 * length_m
```

One wider search also surfaced a Lecos category page snapshot with lower
63 A prices for 25 m and 50 m (`599.00 EUR`, `999.00 EUR`). Using that
variant instead gives:

```text
price_eur = 237.35 + 15.40 * length_m
```

The recommended fit above keeps the originally observed product-line
points because they were internally monotonic and closer to the specific
5G16 listing found first. Treat the 63 A slope as shop- and date-sensitive.

### `Cable125A`: 400 V / 125 A / H07RN-F 5G35

Source: Lecos-Elektronik, "CEE-Verlaengerung 125A 5G35 H07RN-F".

<https://lecos-elektronik.de/cee-verlaengerung/cee-verlaengerung-125a-5g35>

| Length | Listed price |
|-------:|-------------:|
| 5 m    | 399.00 EUR |
| 10 m   | 649.00 EUR |
| 15 m   | 899.00 EUR |

Fit:

```text
price_eur = 149.00 + 50.00 * length_m
```

This is only a three-point fit, but the points are exactly linear. It is
adequate for optimiser weighting. Larger 125 A products are more likely
to be quote-priced, so the exact slope should be revisited before using
it for procurement.

## Relation to current `tier_cost`

The current tier costs in `models.py` are:

| Repo class | Current `tier_cost` | Fitted slope relative to 16 A |
|------------|--------------------:|------------------------------:|
| `Cable16A` | 1.0  | 1.0 |
| `Cable32A` | 3.0  | 2.5 |
| `Cable63A` | 8.0  | 9.4 |
| `Cable125A`| 20.0 | 22.5 |

So the existing heuristic is directionally reasonable:

- 32 A is slightly over-weighted compared with these finished-lead
  examples.
- 63 A is close enough for topology decisions, though the market data
  is noisy.
- 125 A is also close, especially if the optimiser only needs relative
  pressure against long heavy trunks.

The important improvement is that a real purchase model has a non-zero
fixed term. A pure `length * tier_cost` objective slightly over-penalises
long light cables relative to many short heavy cables, because it ignores
the per-lead overhead.

## Caveats

- Prices were gathered from live EU web listings in May 2026 and can
  change without notice.
- VAT treatment follows the listing presentation; shipping is excluded.
- Listings are mostly German/Austrian EU retail examples, not Spanish
  supplier quotes.
- Connector family, IP rating, brand, and phase inverter options can move
  the fixed cost substantially.
- These formulas are for cost weighting in planning, not procurement or
  electrical compliance.
