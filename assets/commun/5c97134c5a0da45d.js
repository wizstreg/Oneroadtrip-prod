(function ortTpBadge(){
  if(!(window.matchMedia&&matchMedia('(min-width:901px)').matches))return;
  var lang=(document.documentElement.lang||'fr').slice(0,2).toLowerCase();
  var T={fr:'Noter sur Trustpilot',en:'Rate on Trustpilot',es:'Valorar en Trustpilot',it:'Valuta su Trustpilot',pt:'Avaliar no Trustpilot',de:'Auf Trustpilot bewerten',nl:'Beoordelen op Trustpilot',ar:'قيّمنا على Trustpilot'};
  var url=lang==='fr'?'https://fr.trustpilot.com/review/oneroadtrip.com':'https://www.trustpilot.com/review/oneroadtrip.com';
  var calme=!!(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  function add(){
    if(document.getElementById('ortTp'))return;
    var st=document.createElement('style');
    st.textContent='#ortTp{position:fixed;left:16px;bottom:16px;z-index:10048;display:inline-flex;align-items:center;gap:7px;padding:9px 16px;background:#00b67a;color:#fff!important;border:0;border-radius:999px;box-shadow:0 6px 18px rgba(0,80,50,.3);font:700 14px/1.2 Inter,system-ui,sans-serif;text-decoration:none!important}'
      +'#ortTp:hover{background:#00995f}'
      +'#ortTp b{color:#fff;font-size:17px;line-height:1}'
      +'#ortTp.pulse{animation:ortTpPulse 1.1s ease-in-out 2}'
      +'@keyframes ortTpPulse{0%,100%{transform:scale(1);box-shadow:0 6px 18px rgba(0,80,50,.3)}50%{transform:scale(1.08);box-shadow:0 0 0 9px rgba(0,182,122,.28)}}'
      +'[dir="rtl"] #ortTp{left:auto;right:16px}'
      +'#ortTp:focus-visible{outline:3px solid #e49d16;outline-offset:2px}'
      +'@media print{#ortTp{display:none}}';
    document.head.appendChild(st);
    var a=document.createElement('a');a.id='ortTp';a.href=url;a.target='_blank';a.rel='noopener';
    var s=document.createElement('b');s.setAttribute('aria-hidden','true');s.textContent='★';
    a.appendChild(s);a.appendChild(document.createTextNode(T[lang]||T.en));
    document.body.appendChild(a);
    if(calme)return;
    var survol=false;
    a.addEventListener('mouseenter',function(){survol=true;});
    a.addEventListener('mouseleave',function(){survol=false;});
    function pulse(){if(survol||document.visibilityState==='hidden')return;a.classList.remove('pulse');void a.offsetWidth;a.classList.add('pulse');}
    setTimeout(pulse,4000);setInterval(pulse,60000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',add);else add();
})();