import json
import re
from collections import Counter, defaultdict
from dateparser import parse as parse_date
from rapidfuzz import fuzz

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Optional synonym map
SYNONYMS = {
    "explosion": "bombing",
    "terrorist attack": "attack",
    "aid suspension": "attack",
    "grenade": "hand grenades",
    "hand grenade": "hand grenades",
    "el salvador": "san salvador",
    "fpmr": "manuel rodriguez patriotic front",
}

def clean_string(s):
    if not s:
        return ""
    s = str(s).lower().strip()
    s = re.sub(r'\([^)]*\)', '', s)  # remove parentheses content
    s = re.sub(r'[^a-z0-9\s]', '', s)  # remove punctuation
    s = re.sub(r'\b(the|a|an)\b', '', s)  # remove articles
    s = re.sub(r'\s+', ' ', s)  # collapse spaces
    return s.strip()

def normalize(s):
    s = clean_string(s)

    # Normalize dates
    parsed = parse_date(s)
    if parsed:
        return parsed.strftime('%Y-%m-%d')

    # Apply synonym map
    return SYNONYMS.get(s, s)

def convert_to_dict_by_doc_id(data, is_gold=False):
    result = defaultdict(list)
    for item in data:
        doc_id = item["doc_id"]
        if is_gold:
            result[doc_id].append(item)  # multiple gold templates per doc
        else:
            result[doc_id] = item  # one predicted template per doc
    return result

def evaluate(gold_data_raw, pred_data_raw, verbose=False, use_fuzzy=False):
    gold_data = convert_to_dict_by_doc_id(gold_data_raw, is_gold=True)
    pred_data = convert_to_dict_by_doc_id(pred_data_raw, is_gold=False)

    all_fields = set()
    for doc_list in gold_data.values():
        for doc in doc_list:
            all_fields.update(doc.keys())
    all_fields.discard("doc_id")

    correct = Counter()
    total_pred = Counter()
    total_gold = Counter()
    mismatches = []

    for doc_id in sorted(gold_data.keys()):
        gold_templates = gold_data[doc_id]
        pred_template = pred_data.get(doc_id, {}).get("filledTemplate", {})

        if verbose:
            print(f"\n🔍 Evaluating DOC: {doc_id}")

        for field in all_fields:
            gold_field_values = {
                normalize(t.get(field)) for t in gold_templates if t.get(field)
            }
            pred_value = normalize(pred_template.get(field))

            if gold_field_values:
                total_gold[field] += 1
            if pred_value:
                total_pred[field] += 1

                matched = pred_value in gold_field_values

                # Allow fuzzy match if enabled
                if not matched and use_fuzzy:
                    for gold_val in gold_field_values:
                        if fuzz.ratio(pred_value, gold_val) >= 90:
                            matched = True
                            break

                if matched:
                    correct[field] += 1
                else:
                    mismatches.append((doc_id, field, pred_value, gold_field_values))
                    if verbose:
                        print(f"❌ Field: {field}")
                        print(f"   → Predicted: {pred_value}")
                        print(f"   → Gold: {gold_field_values}")
            elif verbose and gold_field_values:
                print(f"⚠️  Field: {field} missing in prediction")

    print("\n📊 Evaluation Metrics:")
    print(f"{'Field':<20} {'P':>6} {'R':>6} {'F1':>6} {'Gold':>6} {'Pred':>6} {'Correct':>8}")
    for field in sorted(all_fields):
        p = correct[field] / total_pred[field] if total_pred[field] else 0.0
        r = correct[field] / total_gold[field] if total_gold[field] else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        print(f"{field:<20} {p:6.2f} {r:6.2f} {f1:6.2f} {total_gold[field]:6} {total_pred[field]:6} {correct[field]:8}")

    if verbose and mismatches:
        print("\n🔎 Detailed Mismatches:")
        for doc_id, field, pred, gold_vals in mismatches:
            print(f"- DOC {doc_id}, FIELD {field}: Predicted '{pred}' vs Gold {gold_vals}")

if __name__ == "__main__":
    gold = load_json("muc4_gold.json")
    pred = load_json("muc4_results.json")
    evaluate(gold, pred, verbose=True, use_fuzzy=True)
