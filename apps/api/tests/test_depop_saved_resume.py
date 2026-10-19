from urllib.parse import urlparse, parse_qs

import pytest

from test_depop_scheduling import db, seed, schedule
from app.services.depop_jobs import depop_runner_url, resume_unsubmitted_depop_job


def test_resume_preserves_saved_draft_instead_of_creating_another(db):
    seed(db)
    job = schedule(db)[0]
    job.status = 'needs_review'
    job.runner_url = 'https://www.depop.com/sellinghub/drafts/edit/96913967-122e-4eb6-92b8-f9633f8a967d/'
    db.commit()
    resumed = resume_unsubmitted_depop_job(db, job.id)
    url = urlparse(resumed.runner_url)
    assert url.path.endswith('/96913967-122e-4eb6-92b8-f9633f8a967d/')
    assert parse_qs(url.query)['autozs_job_id'] == [str(job.id)]
    assert resumed.status == 'running'


@pytest.mark.parametrize('url', [
    'https://wrong.test/sellinghub/drafts/edit/96913967-122e-4eb6-92b8-f9633f8a967d/',
    'https://www.depop.com/sellinghub/drafts/edit/not-a-draft/'
])
def test_bad_saved_url_never_falls_back_to_creating_a_duplicate(url):
    with pytest.raises(ValueError):
        depop_runner_url(8, 'closet', url)
