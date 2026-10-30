"""P0 with an observable explanation; the original classification rules stay frozen."""
import re
from .prompt import SYSTEM

OUTPUT_RULE = 'Return exactly Yes or No,\nwithout explanations, punctuation, or markdown.'
EXPLANATION_SYSTEM = SYSTEM.removesuffix(OUTPUT_RULE) + '''Before giving the final label, explain your comparison in detail
using the supplied definitions. Support your judgments with short
source quotes, state how they lead to your decision, and identify
any uncertainty or unsupported assumption.

End with a separate final line in exactly this format:
Final label: Yes
or
Final label: No'''
if OUTPUT_RULE not in SYSTEM or SYSTEM.endswith(OUTPUT_RULE) is False:
    raise ValueError('P0 output instruction changed; review explanation prompt')


def parse_explanation(text):
    lines = text.strip().splitlines()
    if not lines or not re.fullmatch(r'Final label: (Yes|No)', lines[-1]):
        raise ValueError('invalid_response: expected a final Final label: Yes/No line')
    explanation = '\n'.join(lines[:-1]).strip()
    if not explanation or any(line.startswith('Final label:') for line in lines[:-1]):
        raise ValueError('invalid_response: missing explanation or duplicate label')
    return lines[-1].split(': ')[1], explanation
