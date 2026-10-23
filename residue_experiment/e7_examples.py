"""Frozen manual selection, version 1; order is N1, Y1, N2, Y2.

Exploratory selection informed by 2023-2025 zero-shot errors. Roles/reasons
are audit metadata, never extra model instructions.
"""

VERSION = 'error-informed-v1'
SELECTION = {
    2023: (
        ('N1', '2022-16-03', 'No', 'EU adds separate TDM residue definitions.'),
        ('Y1', '2022-22-03', 'Yes', 'Both sides consider the same two compounds separately.'),
        ('N2', '2022-02-02', 'No', 'EU additionally includes metabolite FK-772.'),
        ('Y2', '2022-13-02', 'Yes', 'Chemical name and CGA321113 code describe corresponding definitions.'),
    ),
    2024: (
        ('N1', '2023-20-02', 'No', 'JMPR sums parent equivalents; EU sets separate definitions.'),
        ('Y1', '2023-10-02', 'Yes', 'Common-metabolite scope and expression basis correspond.'),
        ('N2', '2023-21-02', 'No', 'Only JMPR includes quinclorac conjugates.'),
        ('Y2', '2023-15-02', 'Yes', 'Common name and constituent-isomer wording correspond.'),
    ),
    2025: (
        ('N1', '2024-03-04', 'No', 'Latest EU assessment adds tissue/milk-specific definitions.'),
        ('Y1', '2024-01-04', 'Yes', 'Both sides list the same six pyrethrin components.'),
        ('N2', '2024-21-04', 'No', 'Only JMPR additionally includes IN-MYX98.'),
        ('Y2', '2024-23-04', 'Yes', 'B-1 names and added isomer wording correspond in MRL review.'),
    ),
}


def select(pool, year):
    if year not in SELECTION:
        raise ValueError(f'E7 has no frozen selection for {year}')
    chosen = []
    for role, ident, label, reason in SELECTION[year]:
        matches = [r for r in pool if r['id'] == ident]
        if len(matches) != 1:
            raise ValueError(f'E7 requires exactly one previous-year candidate: {ident}')
        row = matches[0]
        if str(row['year']) != str(year - 1) or row['EFSA'] != label:
            raise ValueError(f'E7 candidate year/label mismatch: {ident}')
        chosen.append(dict(row, role=role, selection_reason=reason))
    return chosen
