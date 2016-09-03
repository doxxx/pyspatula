#!/usr/bin/env python

import argparse
import json
import re
import itertools

from requests_cache import CachedSession
import sys

SESSION = CachedSession(expire_after=4*60*60)

ITEM_URL_FORMAT = 'http://www.wowdb.com/api/item/%d'
SPELL_URL_FORMAT = 'http://www.wowdb.com/api/spell/%d'

FEAST_RE = re.compile('(?i)Set out a .+? to feed|Feed up to [0-9]+ people')
RESTORES_RE = re.compile('(?i)Restores ([0-9,\\.%]+) (health|mana)(?: and ([0-9,\\.%]+) mana)?')
BUFF_RE = re.compile('(?i)If you spend at least [0-9]+ seconds eating you will become well fed.+')


def read_item_ids(file):
    lines = file.readlines()
    split_lines = [line.split(',') for line in lines]
    return map(int, itertools.chain(*split_lines))


def make_item_url(item_id):
    return ITEM_URL_FORMAT % (item_id,)


def fetch_item(item_id):
    url = make_item_url(item_id)
    print("Fetching", url, file=sys.stderr)
    return SESSION.get(url)


def fetch_items(item_ids):
    items = [fetch_item(item_id) for item_id in item_ids]
    return items


def extract_effects(item):
    effects = []
    for spell in item.get("Spells", []):
        text = spell["Text"]
        if not FEAST_RE.search(text) is None:
            pass
        restores = RESTORES_RE.search(text)
        if not restores is None:
            value = restores.group(1).replace(',', '')
            if not restores.group(3) is None:
                effect_type = "combo"
                value2 = restores.group(3).replace(',', '')
            else:
                effect_type = restores.group(2)
                value2 = None
            buff = not BUFF_RE.search(text) is None
            effects.append({"type": effect_type, "value": value, "value2": value2, "buff": buff})

    return effects


def parse_item(text):
    # WoWDB API returns JSON surrounded with parentheses which must be stripped
    text = text[1:-1]
    item = json.loads(text)
    effects = extract_effects(item)
    if effects is None or len(effects) == 0:
        return None
    effect = effects[0]
    return {
        "id": item["ID"],
        "name": item["Name"],
        "conjured": item["Flags1"] & 0x2 != 0,
        "type": effect["type"],
        "value": effect["value"],
        "value2": effect["value2"],
        "buff": effect["buff"]
    }


def fetch_and_parse_items(item_ids):
    return list(filter(None, [parse_item(item.text) for item in fetch_items(item_ids)]))

HEALTH_CATEGORIES = {
    (True, "combo", False): "MMM.Consumable.Food.Combo.Conjured",
    (True, "health", False): "MMM.Consumable.Food.Basic.Conjured",
    (True, "combo", True): "MMM.Consumable.Food.Buff.Combo.Conjured",
    (True, "health", True): "MMM.Consumable.Food.Buff.Basic.Conjured",
    (False, "combo", False): "MMM.Consumable.Food.Combo.Non-Conjured",
    (False, "health", False): "MMM.Consumable.Food.Basic.Non-Conjured",
    (False, "combo", True): "MMM.Consumable.Food.Buff.Combo.Non-Conjured",
    (False, "health", True): "MMM.Consumable.Food.Buff.Basic.Non-Conjured",
}

MANA_CATEGORIES = {
    (True, "combo", False): "MMM.Consumable.Food.Combo.Conjured.Mana",
    (True, "mana", False): "MMM.Consumable.Food.Basic.Conjured.Mana",
    (True, "combo", True): "MMM.Consumable.Food.Buff.Combo.Conjured.Mana",
    (True, "mana", True): "MMM.Consumable.Food.Buff.Basic.Conjured.Mana",
    (False, "combo", False): "MMM.Consumable.Food.Combo.Non-Conjured.Mana",
    (False, "mana", False): "MMM.Consumable.Food.Basic.Non-Conjured.Mana",
    (False, "combo", True): "MMM.Consumable.Food.Buff.Combo.Non-Conjured.Mana",
    (False, "mana", True): "MMM.Consumable.Food.Buff.Basic.Non-Conjured.Mana",
}


def categories_for_item(item):
    key = (item["conjured"], item["type"], item["buff"])
    return HEALTH_CATEGORIES.get(key, None), MANA_CATEGORIES.get(key, None)

def item_value(item, category):
    value_key = "value"
    if item["type"] == "combo" and category.endswith(".Mana"):
        value_key = "value2"
    value = item[value_key]
    if not '%' in value:
        # truncate numbers which are not percentages
        value = str(int(float(item["value"])))
    return value


def categorize_items(items):
    categorized_items = {}
    percent_items = []
    for item in items:
        if (item["value"] and '%' in item["value"]) or (item["value2"] and '%' in item["value2"]):
            percent_items.append(item)
        for category in categories_for_item(item):
            if not category is None:
                category_list = categorized_items.get(category, [])
                category_list.append(item)
                categorized_items[category] = category_list
    return categorized_items, percent_items


def output_lua(categorized_items, output_file):
    for category in categorized_items:
        items = categorized_items[category]
        items_text = ",".join(["%d:%s" % (item["id"], item_value(item, category)) for item in items])
        print("PT:AddData(\"%s\",\"%s\")" % (category, items_text), file=output_file)


def output_percent_items(percent_items):
    if len(percent_items) > 0:
        for item in percent_items:
            print(item["id"], file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="output file, defaults to stdout")
    parser.add_argument("FILE", nargs='+', help="one or more files containing item IDs")
    args = parser.parse_args()

    items = []
    for item_ids_file_name in args.FILE:
        with open(item_ids_file_name) as item_ids_file:
            item_ids = set(read_item_ids(item_ids_file))
            items.extend(fetch_and_parse_items(item_ids))

    categorized_items, percent_items = categorize_items(items)

    if args.output is None:
        print("Writing to stdout", file=sys.stderr)
        output_file = sys.stdout
    else:
        print("Writing to", args.output, file=sys.stderr)
        output_file = open(args.output, "wt")

    try:
        output_lua(categorized_items, output_file)
    finally:
        output_file.close()

    print("Items using percentage values:", file=sys.stderr)
    output_percent_items(percent_items)


if __name__ == '__main__':
    main()
