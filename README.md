\# JLPT Grammar App



A Flask-based JLPT grammar quiz app for studying Japanese grammar.



\## Features



\- User selection

\- Dashboard with progress summary

\- Start Quiz with filters

\- JLPT level filter

\- Difficulty filter

\- Mastery level filter

\- Include / exclude mastery filter

\- Question count and unlimited mode

\- Detailed answer feedback

\- Grammar search

\- Question history

\- Statistics

\- Reset progress

\- Mastery explanation page

\- Question selection explanation page



\## Quiz Filters



The quiz can be filtered by:



\- JLPT level: All, N1, N2

\- Difficulty: All, easy, normal, hard

\- Mastery level: new, learning, weak, mastered

\- Question count: 5, 10, 20, unlimited



\## Mastery Levels



Each grammar point has a mastery level:



\- New: not practiced much yet

\- Learning: started practicing

\- Weak: repeated mistakes and low accuracy

\- Mastered: repeated correct answers with high accuracy



\## Main Files



\- `web\_app.py`: Main Flask web app

\- `database.py`: Database helper functions

\- `data/jlpt\_app.db`: SQLite database

\- `templates/`: HTML pages

\- `static/style.css`: CSS design



\## Run Locally



Install requirements:



```powershell

pip install -r requirements.txt

