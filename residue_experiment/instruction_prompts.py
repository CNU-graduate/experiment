"""Frozen instruction-only variants; no examples, item IDs, or answer labels."""
from .prompt import SYSTEM

VERSION = 'instruction-v1'
VARIANTS = ('P1', 'P2')

COMMON = """Apply the following comparison procedure:

1. Identify the definitions applicable to the stated purpose and
   commodity. Distinguish legal, peer-review, MRL-review, proposed,
   and provisional definitions. Do not merge definitions from different
   sources or select only a matching sentence while ignoring another
   applicable definition.

2. Resolve chemical names, common names, metabolite codes, and isomer
   descriptions where equivalence is supported. Different wording
   alone does not establish a substantive difference. Do not invent
   synonym relationships.

3. Distinguish combined sums from independently assessed definitions.
   "Considered separately" does not mean a combined sum.
   Numbering alone does not establish whether compounds are summed
   or assessed independently.

4. Compare the applicable chemical scope, including metabolites,
   isomers, free and conjugated forms, and the expression basis.
   Shared parent compounds alone do not establish comparability.

5. Apply each qualification only to the source, species, tissue,
   commodity, or use it describes. A provisional status or a
   "not required" statement alone does not determine Yes or No.

Base the final decision on the applicable definitions as a whole.
Do not automatically favor Yes or No.
Return exactly Yes or No."""

MODEL_SPECIFIC = {
    'openai': """Before rejecting comparability, distinguish a genuine difference in
chemical scope from a difference in terminology, level of detail,
or analytical description.

A common name and an explicit component or isomer description may
refer to the same residue, but equivalence must be supported rather
than assumed.

Do not extend a restriction applying to one source or commodity to
all definitions. These checks must not override genuine differences
in included compounds, assessment structure, or expression basis.""",
    'gemini': """Explicitly distinguish independently assessed compounds from a
combined residue definition. Do not add independently listed compounds
into a single sum, and do not discard an additional applicable
definition merely because it is assessed separately.

Preserve substantive distinctions between free residues, conjugated
residues, and a specifically named conjugate. Do not treat these scopes
as interchangeable without support.

Neither an omitted qualifier nor an additional phrase alone is
sufficient to determine Yes or No.""",
    'anthropic': """Before accepting comparability, check for substantive differences that
remain after matching the shared parent compound.

Account for additional applicable metabolites or residue definitions,
combined versus independent assessment, conjugate scope, and
expression basis. A shared compound name or a matching older
definition does not cancel another applicable difference.

Do not assume that every additional phrase creates non-comparability:
first establish whether it changes the applicable scope or assessment
structure."""
}


def system_for(provider, variant):
    if provider not in MODEL_SPECIFIC or variant not in VARIANTS:
        raise ValueError('Expected a supported provider and P1 or P2; P0 is not run')
    text = SYSTEM.rstrip() + '\n\n' + COMMON
    if variant == 'P2':
        text += '\n\n' + MODEL_SPECIFIC[provider]
    return text
