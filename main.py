from argparse import ArgumentParser
from glob import glob
import json
from operator import itemgetter
from os.path import join as path_join

from pyttp.css import AugmentingRule, Rule, Ruleset
from pyttp.form import Field, Form, TextField
from pyttp.controller import (
    Controller,
    ControllerResponse,
    expose,
    inject_header,
    TemplateResponse,
    validate,
)
from pyttp.js import toJS
from pyttp.pagination import paginate
from pyttp.scaffold import make_controller_root, wrap_root
from pyttp.validators import ValidationException

from reset_css import reset


SEARCHABLE_FIELDS = ('song', 'artist', 'album')
SORTABLE_FIELDS = (
    'time',
    'popularity',
    'dance',
    'energy',
    'happy',
    'acoustic',
    'instrumental',
    'speech',
    'live',
    'tempo',
)
DISPLAYED_FIELDS = SEARCHABLE_FIELDS + SORTABLE_FIELDS

def css():
    return reset + Ruleset(
        Rule("body", padding="10px"),
        Rule(".hidden", display="none"),
        Rule(".header", margin_bottom="15px", margin_left="10px", sub_rules=[
            Rule("button", margin_left="20px", sub_rules=[
                AugmentingRule("#next", margin_left="0px"),
            ]),
        ]),
        Rule("td, th", padding_left="10px", text_align="left"),
        Rule("input.sort", width="50px"),
    )


def js():
    exports = {}

    def setup(jq):
        songs: let = jq("#songs")
        template: let = jq("#template")
        page: let = jq("#page")
        min_page = 1
        max_page = 1

        @jq("#reset").click
        def reset():
            jq(".sort").val(0)
            jq("#page").val(1)
            jq("#controls").change()

        @jq("#prev").click
        def previous():
            previous_page: let = int(page.val()) - 1
            if previous_page >= min_page:
                page.val(previous_page)
            jq("#controls").change()

        @jq("#next").click
        def next():
            next_page: let = int(page.val()) + 1
            if next_page <= max_page:
                page.val(next_page)
            jq("#controls").change()

        @jq("#controls").change
        def update(evt):
            evt.preventDefault()
            form: let = jq(this)
            url: let = form.prop("action")

            def ajaxSuccess(data):
                songs.empty()
                for song in data["songs"]:
                    row = template.clone()
                    for field in fields:
                        row.find("." + field).text(song[field])
                    row.removeClass("hidden")
                    row.removeAttr("id")
                    row.appendTo(songs)
                max_page = data["max_page"]
                page.attr("max", max_page)
                if page.val() > max_page:
                    page.val(max_page)

            jq.ajax({
                "url": url,
                "dataType": "json",
                "data": form.serializeArray(),
                "success": ajaxSuccess,
            })
            form.serialize()
            return False

        @jq("#controls").submit
        def submit(evt):
            evt.preventDefault()
            return False

        jq("#controls").change()

    exports.setup = setup
    return exports


def load_data(data_dir):
    data = {}
    json_files = glob(path_join(data_dir, "*.json"))
    for json_file in json_files:
        with open(json_file) as f:
            json_data = json.load(f)
            data.update({row['spotify_track_id']: row for row in json_data})
    return data


class SortDirectionField(Field):
    def render(self):
        return f'''
            <input class="sort" type="range" min="-1" max="1" step="1" name="{self.name}" id="{self.id}" value="0.0">
        '''

def validate_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationException("Not a valid integer.") from exc
    return value

class IntegerField(TextField):
    default_validators = [validate_int]

    def __init__(self, name=None, min_value=None, max_value=None, **kwargs):
        super().__init__(name=name, **kwargs)
        self.min_value = min_value
        self.max_value = max_value

    def is_valid(self):
        valid = super().is_valid()
        if valid:
            if self.min_value and self._value < self.min_value:
                self.errors.append(f"Value smaller than {self.min_value}.")
                return False
            if self.max_value and self._value > self.max_value:
                self.errors.append(f"Value larger than {self.max_value}.")
                return False
        return valid

    def render(self):
        outp = [
            '<input type="number"',
        ]
        if self.min_value is not None:
            outp.append(f' min="{self.min_value}"')
        if self.max_value is not None:
            outp.append(f' min="{self.max_value}"')
        outp.append(f' name="{self.name}" id="{self.id}" value="{self.value}">')
        return ''.join(outp)


class FilterForm(Form):
    search = TextField("search")
    page = IntegerField("page", min_value=1, value=1)
    time = SortDirectionField("time")
    popularity = SortDirectionField("popularity")
    happy = SortDirectionField("happy")
    dance = SortDirectionField("dance")
    energy = SortDirectionField("energy")
    acoustic = SortDirectionField("acoustic")
    instrumental = SortDirectionField("instrumental")
    speech = SortDirectionField("speech")
    live = SortDirectionField("live")
    tempo = SortDirectionField("tempo")


class MusicController(Controller):

    def __init__(self, data, songs_per_page=50):
        self.data = list(data.values())
        self.songs_per_page = songs_per_page
        self.css = None
        self.js = None
        self.field_value_percent = {
            'tempo': self.tempo_to_percent,
            'time': self.time_to_percent,
        }
        self.max_tempo = max(song["tempo"] for song in self.data)
        self.max_time = max(self.time_to_int(song["time"]) for song in self.data)

    def time_to_int(self, value):
        minutes, seconds = value.split(":")
        return int(minutes) * 60 + int(seconds)

    def time_to_percent(self, value):
        return self.time_to_int(value) * 100 // self.max_time

    def tempo_to_percent(self, value):
        return value * 100 // self.max_tempo

    def get_sort_key(self, mapping):

        def key(song):
            score = 0
            for field, factor in mapping.items():
                value = song[field]
                if field in self.field_value_percent:
                    value = self.field_value_percent[field](value)
                score += value * factor
            return score
        return key

    @expose
    @inject_header(('Content-Type', 'application/json'))
    def json(self, request):
        form = FilterForm(request.GET)
        sort_key = itemgetter("song")
        reverse = False
        page = 1
        if form.is_valid():
            page = int(form.fields["page"].value)
            songs = []
            search = form.fields["search"].value.lower().strip()
            for song in self.data:
                for field in SEARCHABLE_FIELDS:
                    if search in song[field].lower():
                        songs.append(song)
                        break
            sorting_fields = {}
            for field in SORTABLE_FIELDS:
                value = float(form.fields[field].value)
                if value:
                    sorting_fields[field] = value
            if sorting_fields:
                sort_key = self.get_sort_key(sorting_fields)
                reverse = True
        else:
            songs = self.data
        songs = sorted(songs, key=sort_key, reverse=reverse)
        num_songs = len(songs)
        max_page = (num_songs // self.songs_per_page) + 1
        if page > max_page:
            page = max_page
        max_song = page * self.songs_per_page
        min_song = (page - 1) * self.songs_per_page
        songs = songs[min_song:max_song]
        return ControllerResponse(json.dumps({"songs": songs, "page": page, "max_page": max_page}))

    @expose
    def index(self, request):
        form = FilterForm()
        sortable_fields = [form.fields[name] for name in SORTABLE_FIELDS]
        context = dict(
            form=form,
            searchable_fields=SEARCHABLE_FIELDS,
            sortable_fields=sortable_fields,
        )
        return TemplateResponse("templates/index.pyml", context=context)

    @expose
    @inject_header(('Content-Type', 'application/javascript'))
    def js_src(self, request):
        if self.js is None:
            context = dict(fields=DISPLAYED_FIELDS)
            self.js = toJS(js, context=context)

        return ControllerResponse(self.js)

    @expose
    @inject_header(('Content-Type', 'text/css'))
    def css_src(self, request):
        if self.css is None:
            self.css = str(css())
        return ControllerResponse(self.css)

def get_args():
    parser = ArgumentParser()
    parser.add_argument("--data-dir", default="data/", required=False)
    parser.add_argument("--songs-per-page", default=50, required=False)
    parser.add_argument("--threads", default=20, required=False)
    args, _ = parser.parse_known_args()
    return args

def wsgi(options=None):
    if options is None:
        options = get_args()
    data = load_data(options.data_dir)
    controller = MusicController(data, songs_per_page=options.songs_per_page)
    root = make_controller_root(controller, static_serve_dir="static/")
    return root

def main():
    options = get_args()
    root = wsgi(options)
    wsgi_app = wrap_root(root, nThreads=options.threads)
    wsgi_app.serve()

if __name__ == "__main__":
    main()