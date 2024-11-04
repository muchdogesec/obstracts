python manage.py migrate
python obstracts/cjob/arango_view_helper.py && gunicorn obstracts.wsgi:application  --reload --bind 0.0.0.0:8001
