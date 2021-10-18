# hacksprint
## How to run
* Create virtualenv with Python 3.9+
* Install [PyTTP](https://github.com/daineX/PyTTP) in venv from source
* Find a spotify playlist you're interested in
* Use https://www.chosic.com/spotify-playlist-analyzer/ to export said playlist as CSV (see bottom of page)
* Put CSV into a /data folder inside the project
* Run `python csv_to_json.py <path_to_csv>` on the CSV file
* Run app with `python main.py`
