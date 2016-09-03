# pyspatula

Uses the wowdb.com API to build LibPeriodicTable custom datasets for WoW food and drink items.

## Requirements

Python 3.4+ and the packages listed in `requirements.txt` are required. The packages can be installed using `pip install -r requirements.txt`.

## Running

Running `main.py` with the `--help` option for details on usage.

One or more files containing item IDs are required. These files may contain multiple lines with multiple item IDs listed on each line separated by commas.

Item ID lists currently included:

* muffinlib_items.txt: item IDs manually extracted from [MuffinLibPTSets](http://wow.curseforge.com/addons/libpt-muffinsets/).
