/* Gerado por gen_noticias.py — slots Google AdSense configuráveis via Supabase */
(function(){
  var URL="https://news.mob.tec.br";
  var KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyAgCiAgICAicm9sZSI6ICJhbm9uIiwKICAgICJpc3MiOiAic3VwYWJhc2UtZGVtbyIsCiAgICAiaWF0IjogMTY0MTc2OTIwMCwKICAgICJleHAiOiAxNzk5NTM1NjAwCn0.dc_X5iR_VP_qT0zsiyj_I_OZ2T9FtRU2BBNWN8Bu4GE";
  var slots=document.querySelectorAll('.adsbygoogle');
  if(!URL||!KEY||!slots.length)return;
  function hide(){slots.forEach(function(s){var w=s.closest('.ad-slot');if(w)w.hidden=true;});}
  function enable(cfg){
    slots.forEach(function(s){
      s.setAttribute('data-ad-client',cfg.adsense_client_id||'');
      if(cfg.feed_slot_id)s.setAttribute('data-ad-slot',cfg.feed_slot_id);
    });
    var sc=document.createElement('script');
    sc.async=true;
    sc.src='https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='+encodeURIComponent(cfg.adsense_client_id||'');
    sc.crossOrigin='anonymous';
    sc.onload=function(){slots.forEach(function(){try{(window.adsbygoogle=window.adsbygoogle||[]).push({});}catch(e){}});};
    document.head.appendChild(sc);
  }
  fetch(URL+'/rest/v1/rpc/fn_get_monetization_config',{
    method:'POST',
    headers:{'apikey':KEY,'Authorization':'Bearer '+KEY,'Content-Type':'application/json'},
    body:'{}'
  }).then(function(r){return r.ok?r.json():null;})
    .then(function(cfg){
      cfg=Array.isArray(cfg)?(cfg[0]||null):(cfg||null);
      if(cfg&&cfg.adsense_enabled&&cfg.adsense_client_id)enable(cfg);
      else hide();
    }).catch(hide);
})();
