# Local craft comparison, not send blocking

    py -m pip install -r requirements-quality.txt
    py -m quality.craft runs/RUN_ID.json --output runs/craft/RUN_ID --approved-domain events.example --approved-domain portal.example

Use the actual approved domains for the run. The tool processes every saved email
and attached landing page at 700/1200 pixels in headless Chrome with page scripts,
network, service workers and form submission disabled. It writes PNGs, a render
manifest, craft.json and an annotated bundle copy. It does not modify original
API logs, contact results or the sending path.

Four 0-2 mechanical proxies cover sender detail presence, channel format,
cleanliness and detail consistency. The comparison total is 0-8, explicitly
provisional, not revel8's 10-point craft result. Tone, authenticity, semantic
facts and brand fit are not judged. Missing renders stay unknown rather than zero.

Overflow, clipping, excessive height, broken images and font-family counts are
recorded. Images are not resolved; network images cannot load. No vision model
is configured or called. These artifacts are for comparing writer versions and
visual inspection, never for changing incident/touch metrics or blocking sends.
