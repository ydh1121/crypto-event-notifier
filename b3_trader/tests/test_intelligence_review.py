import json

from b3_trader.runtime_review import _result_evidence


def test_partial_source_failures_are_not_hidden_by_healthy_supervisor_status():
    result=_result_evidence({'status':'partial','source_failures':5,'source_results':{
        'us_bls_release_calendar':{'status':'source_error','events':0,
            'error':'ConnectionError: NameResolutionError token=private-dns'},
        'us_sec_press_releases':{'status':'source_error','events':0,
            'error':'HTTPError: 403 Client Error: Forbidden for url=https://private?key=private-key'},
        'us_cftc_press_releases':{'status':'source_error','events':0,
            'error':'ReadTimeout: private-value'},
        'us_bea_release_schedule':{'status':'ok','events':12,'inserted':2,'updated':10},
        'private-source':{'status':'source_error','error':'private-error'}},
        'macro_actual_capture':{'status':'partial','capture_failures':2,'errors':[
            {'event_id':'private-id','error':'SSLError: CERTIFICATE_VERIFY_FAILED private-url'},
            {'event_id':'private-id','error':'ParseError: private-body'}]},
        'consensus_capture':{'status':'capture_error','error':'RuntimeError: transient HTTP 429 private'}})
    assert result['source_failures']==5
    sources=result['source_results']
    assert sources['us_bls_release_calendar']['error_kinds']==['connection','dns']
    assert sources['us_sec_press_releases']['http_status_codes']==[403]
    assert sources['us_cftc_press_releases']['error_kinds']==['timeout']
    assert sources['us_bea_release_schedule']['events']==12
    assert result['macro_actual_capture']['error_kinds']==['parse','tls']
    assert result['consensus_capture']['http_status_codes']==[429]
    assert 'private' not in json.dumps(result)


def test_missing_source_detail_is_not_five_fabricated_successes():
    result=_result_evidence({'source_failures':5})
    assert result=={'source_failures':5}


def test_bad_source_status_and_error_shapes_are_safe_unknowns():
    result=_result_evidence({'source_results':{'us_sec_press_releases':{
        'status':{'private':'data'},'events':float('inf'),'error':{'private':'data'},
        'errors':[None,False,{'error':None}]}},'bea_actual_capture':None})
    source=result['source_results']['us_sec_press_releases']
    assert source['status']=='unrecognized' and source['error_present'] is False
    assert 'events' not in source
    assert result['bea_actual_capture']['status']=='unavailable'
    assert 'private' not in json.dumps(result)
