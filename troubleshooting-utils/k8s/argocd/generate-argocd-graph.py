  #!/usr/bin/env python3
"""Transform ArgoCD resource JSON into a Cytoscape.js graph and open in browser."""

import argparse
import json
import os
import sys
import webbrowser


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/dagre@0.8.5/dist/dagre.min.js"></script>
<script src="https://unpkg.com/cytoscape-dagre@2.5.0/cytoscape-dagre.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#1a1a2e;--surface:#16213e;--input:#0f3460;--text:#e0e0e0;--text-dim:#aaa;--text-muted:#888;--border:#333;--border-row:#222;--tooltip-bg:#222;--tooltip-text:#eee;--hover:#1a4a8a;--panel-title:#fff;--label-text:#fff;--label-outline:#111;--leaf-label:#ccc}
.light{--bg:#f0f2f5;--surface:#ffffff;--input:#e8edf2;--text:#1a1a2e;--text-dim:#555;--text-muted:#777;--border:#ccc;--border-row:#e0e0e0;--tooltip-bg:#333;--tooltip-text:#fff;--hover:#d0d8e8;--panel-title:#111;--label-text:#111;--label-outline:#fff;--leaf-label:#333}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,monospace;overflow:hidden}
#toolbar{position:fixed;top:0;left:0;right:0;height:50px;background:var(--surface);display:flex;align-items:center;gap:8px;padding:0 12px;z-index:10;border-bottom:1px solid var(--border);flex-wrap:nowrap;overflow-x:auto}
#toolbar input,#toolbar select{background:var(--input);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 8px;font-size:12px;height:30px}
#toolbar input{width:180px}
#toolbar select{max-width:140px}
#toolbar button{background:var(--input);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:4px 10px;font-size:12px;cursor:pointer;height:30px;white-space:nowrap}
#toolbar button:hover{background:var(--hover)}
#toolbar button.active{background:#e94560;border-color:#e94560;color:#fff}
.btn-danger{background:#c62828 !important;border-color:#c62828 !important;color:#fff !important}
.btn-warning{background:#e65100 !important;border-color:#e65100 !important;color:#fff !important}
#theme-btn{font-size:16px;padding:4px 8px;line-height:1}
#stats-display{font-size:11px;color:var(--text-dim);white-space:nowrap;margin-left:auto}
#cy{position:fixed;top:50px;left:0;right:0;bottom:30px}
#search-panel{position:fixed;top:50px;left:0;width:340px;bottom:30px;background:var(--surface);border-right:1px solid var(--border);display:none;z-index:5;flex-direction:column}
#search-panel.open{display:flex}
#sp-header{padding:10px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
#sp-header span{font-size:12px;color:var(--text-dim)}
#sp-toggle-row{padding:6px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-dim)}
#sp-toggle-row label{cursor:pointer;display:flex;align-items:center;gap:4px}
.toggle-switch{position:relative;width:32px;height:18px;display:inline-block}
.toggle-switch input{opacity:0;width:0;height:0}
.toggle-slider{position:absolute;inset:0;background:var(--border);border-radius:9px;transition:.2s;cursor:pointer}
.toggle-slider:before{content:'';position:absolute;width:14px;height:14px;left:2px;top:2px;background:var(--text);border-radius:50%;transition:.2s}
.toggle-switch input:checked+.toggle-slider{background:#4caf50}
.toggle-switch input:checked+.toggle-slider:before{transform:translateX(14px)}
#sp-results{flex:1;overflow-y:auto;padding:4px 0}
.sp-group{}
.sp-group-header{padding:6px 12px;font-size:11px;color:var(--panel-title);background:var(--bg);cursor:pointer;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border);user-select:none}
.sp-group-header:hover{background:var(--hover)}
.sp-chevron{font-size:9px;color:var(--text-muted);transition:transform .15s;display:inline-block;width:12px;text-align:center}
.sp-group.collapsed .sp-chevron{transform:rotate(-90deg)}
.sp-group.collapsed .sp-children{display:none}
.sp-group-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.sp-group-count{color:var(--text-muted);font-size:10px;flex-shrink:0}
.sp-children{border-bottom:1px solid var(--border)}
.sp-item{padding:4px 12px 4px 30px;font-size:11px;cursor:pointer;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border-row)}
.sp-item:hover{background:var(--hover)}
.sp-health-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.sp-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sp-kind{color:var(--text-muted);font-size:10px;flex-shrink:0}
#sp-close{background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:16px;padding:0 4px}
#sp-close:hover{color:var(--text)}
#ctx-menu{position:fixed;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 0;display:none;z-index:30;min-width:180px;box-shadow:0 4px 16px rgba(0,0,0,.4)}
#ctx-menu .ctx-item{padding:6px 14px;font-size:12px;cursor:pointer;display:flex;align-items:center;gap:8px;color:var(--text)}
#ctx-menu .ctx-item:hover{background:var(--hover)}
#ctx-menu .ctx-sep{height:1px;background:var(--border);margin:3px 0}
#ctx-menu .ctx-icon{width:16px;text-align:center;font-size:13px;flex-shrink:0}
#ctx-menu .ctx-label{flex:1}
#ctx-menu .ctx-hint{font-size:10px;color:var(--text-muted)}
#detail-panel{position:fixed;top:50px;right:0;width:320px;bottom:30px;background:var(--surface);border-left:1px solid var(--border);padding:16px;overflow-y:auto;display:none;z-index:5}
#detail-panel h3{color:var(--panel-title);margin-bottom:12px;word-break:break-all;font-size:14px}
.detail-row{padding:4px 0;font-size:12px;display:flex;justify-content:space-between;border-bottom:1px solid var(--border-row)}
.detail-row span:first-child{color:var(--text-muted)}
.health-healthy{color:#4caf50}.health-progressing{color:#ff9800}.health-degraded{color:#f44336}.health-unknown{color:#607d8b}.health-missing{color:#ff5722}
.sync-synced{color:#4caf50}.sync-outofsync{color:#ff9800}.sync-unknown{color:#607d8b}
#detail-panel button{margin-top:12px;width:100%}
#tooltip{position:fixed;background:var(--tooltip-bg);color:var(--tooltip-text);padding:4px 8px;border-radius:3px;font-size:11px;pointer-events:none;display:none;z-index:20;white-space:nowrap}
#legend{position:fixed;bottom:0;left:0;right:0;height:30px;background:var(--surface);border-top:1px solid var(--border);display:flex;align-items:center;gap:16px;padding:0 12px;font-size:11px;color:var(--text-dim)}
.legend-item{display:flex;align-items:center;gap:4px}
.legend-dot{width:10px;height:10px;border-radius:50%;display:inline-block}
</style></head>
<body>
<div id="toolbar">
<input type="text" id="search" placeholder="Search... (Enter to search)">
<button id="search-btn">&#x1F50D;</button>
<select id="kindFilter"><option value="">All Kinds</option></select>
<select id="nsFilter"><option value="">All Namespaces</option></select>
<select id="syncFilter"><option value="">All Sync</option></select>
<select id="healthFilter"><option value="">All Health</option></select>
<button class="btn-danger" id="btn-unhealthy">Unhealthy</button>
<button class="btn-warning" id="btn-outofsync">OutOfSync</button>
<button id="expand-all">Expand All</button>
<button id="collapse-all">Collapse All</button>
<button id="fit-btn">Fit</button>
<button id="theme-btn" title="Toggle light/dark theme">&#9790;</button>
<span id="stats-display"></span>
</div>
<div id="search-panel">
<div id="sp-header"><span id="sp-count"></span><button id="sp-close">&times;</button></div>
<div id="sp-toggle-row"><label class="toggle-switch"><input type="checkbox" id="sp-highlight"><span class="toggle-slider"></span></label><span>Highlight on graph</span><button id="sp-expand-results" style="margin-left:auto;font-size:10px;padding:2px 8px;background:var(--input);color:var(--text);border:1px solid var(--border);border-radius:3px;cursor:pointer">Expand all on graph</button></div>
<div id="sp-results"></div>
</div>
<div id="cy"></div>
<div id="detail-panel"></div>
<div id="tooltip"></div>
<div id="ctx-menu">
<div class="ctx-item" data-action="compact"><span class="ctx-icon">&#x25A3;</span><span class="ctx-label">Compact selected</span><span class="ctx-hint">Pack tight</span></div>
<div class="ctx-item" data-action="spread"><span class="ctx-icon">&#x2725;</span><span class="ctx-label">Spread selected</span><span class="ctx-hint">Space out</span></div>
<div class="ctx-sep"></div>
<div class="ctx-item" data-action="circle"><span class="ctx-icon">&#x25CB;</span><span class="ctx-label">Arrange in circle</span></div>
<div class="ctx-item" data-action="grid"><span class="ctx-icon">&#x25A6;</span><span class="ctx-label">Arrange in grid</span></div>
<div class="ctx-sep"></div>
<div class="ctx-item" data-action="select-children"><span class="ctx-icon">&#x2BA9;</span><span class="ctx-label">Select children</span></div>
<div class="ctx-item" data-action="select-siblings"><span class="ctx-icon">&#x2194;</span><span class="ctx-label">Select siblings</span></div>
<div class="ctx-sep"></div>
<div class="ctx-item" data-action="expand"><span class="ctx-icon">&#x25BC;</span><span class="ctx-label">Expand app</span></div>
<div class="ctx-item" data-action="collapse"><span class="ctx-icon">&#x25B6;</span><span class="ctx-label">Collapse app</span></div>
</div>
<div id="legend">
<span style="color:var(--panel-title)">Health:</span>
<span class="legend-item"><span class="legend-dot" style="background:#4caf50"></span>Healthy</span>
<span class="legend-item"><span class="legend-dot" style="background:#ff9800"></span>Progressing</span>
<span class="legend-item"><span class="legend-dot" style="background:#f44336"></span>Degraded</span>
<span class="legend-item"><span class="legend-dot" style="background:#ff5722"></span>Missing</span>
<span class="legend-item"><span class="legend-dot" style="background:#607d8b"></span>Unknown</span>
<span style="margin-left:20px;color:var(--panel-title)">Shape:</span>
<span class="legend-item">&#x2B22; App</span>
<span class="legend-item">&#x25AD; Resource</span>
<span style="margin-left:auto;color:var(--text-muted);font-size:10px">Click = details | Double-click app = expand/collapse | Shift+drag = box select | Esc = reset</span>
</div>
<script>
__JS_CODE__
</script>
</body></html>"""


JS_TEMPLATE = """
const G = __GRAPH_DATA__;
const HEALTH_COLORS = {Healthy:'#4caf50',Progressing:'#ff9800',Degraded:'#f44336',Missing:'#ff5722',Suspended:'#9e9e9e',Unknown:'#607d8b'};
function hc(s){return HEALTH_COLORS[s]||'#607d8b'}

// Populate filter dropdowns
['kindFilter','nsFilter','syncFilter','healthFilter'].forEach((id,i)=>{
  const sel=document.getElementById(id);
  const vals=[G.stats.kinds,G.stats.namespaces,G.stats.syncStatuses,G.stats.healthStatuses][i];
  vals.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;sel.appendChild(o)});
});

const cy = cytoscape({
  container: document.getElementById('cy'),
  elements: [...G.nodes, ...G.edges],
  wheelSensitivity: 0.3,
  boxSelectionEnabled: true,
  selectionType: 'additive',
  style: [
    {selector:'node[?isApp]',style:{'shape':'hexagon','width':60,'height':60,'background-color':function(e){return hc(e.data('healthStatus'))},'border-width':3,'border-color':'#333','label':function(e){var l=e.data('label');var c=e.data('childCount');return (l.length>22?l.slice(0,20)+'..':l)+(c?' ('+c+')':'');},'font-size':'10px','color':'#fff','text-valign':'bottom','text-margin-y':6,'text-outline-width':1,'text-outline-color':'#111','text-wrap':'wrap','text-max-width':'120px'}},
    {selector:'node[?isRoot]',style:{'width':80,'height':80,'border-width':4,'border-color':'#e94560','font-size':'12px'}},
    {selector:'node[!isApp]',style:{'shape':'round-rectangle','width':36,'height':36,'background-color':function(e){return hc(e.data('healthStatus'))},'background-opacity':0.7,'border-width':1,'border-color':'#444','label':function(e){var l=e.data('label');return l.length>18?l.slice(0,16)+'..':l;},'font-size':'8px','color':'#ccc','text-valign':'bottom','text-margin-y':4,'text-outline-width':1,'text-outline-color':'#111'}},
    {selector:'edge',style:{'width':2,'line-color':'#444','target-arrow-color':'#555','target-arrow-shape':'triangle','curve-style':'bezier','arrow-scale':0.8}},
    {selector:'.dimmed',style:{'opacity':0.12}},
    {selector:'.highlighted',style:{'opacity':1,'border-color':'#e94560','border-width':4}},
    {selector:':selected',style:{'border-color':'#00bcd4','border-width':4,'overlay-color':'#00bcd4','overlay-opacity':0.15}}
  ],
  layout:{name:'dagre',rankDir:'TB',nodeSep:80,rankSep:120,edgeSep:40,animate:false}
});

// Expand / Collapse
const expandedApps = new Set();
function expandApp(appId){
  const children = G.appChildren[appId];
  if(!children||!children.length)return;
  if(expandedApps.has(appId))return;
  expandedApps.add(appId);
  const pp=cy.getElementById(appId).position();
  const cols=Math.ceil(Math.sqrt(children.length));
  cy.startBatch();
  children.forEach(function(ch,i){
    var nid='leaf_'+appId+'_'+i;
    if(cy.getElementById(nid).length)return;
    if(ch.kind==='Application'&&cy.getElementById(ch.label).length)return;
    var row=Math.floor(i/cols),col=i%cols;
    cy.add({group:'nodes',data:{id:nid,label:ch.label,kind:ch.kind,apiGroup:ch.apiGroup,version:ch.version,namespace:ch.namespace,syncStatus:ch.syncStatus,healthStatus:ch.healthStatus,isApp:false,isRoot:false,parentApp:appId,childCount:0},position:{x:pp.x-(cols*25)+col*50,y:pp.y+100+row*50}});
    cy.add({group:'edges',data:{source:appId,target:nid}});
  });
  cy.endBatch();
  updateStats();
}
function collapseApp(appId){
  if(!expandedApps.has(appId))return;
  expandedApps.delete(appId);
  cy.startBatch();
  cy.nodes().filter(function(n){return n.data('parentApp')===appId}).remove();
  cy.endBatch();
  updateStats();
}
function toggleApp(appId){expandedApps.has(appId)?collapseApp(appId):expandApp(appId)}

cy.on('tap','node',function(e){showDetail(e.target.data())});
cy.on('dbltap','node[?isApp]',function(e){toggleApp(e.target.data().id)});

// Detail panel
function showDetail(d){
  var p=document.getElementById('detail-panel');
  p.style.display='block';
  p.innerHTML='<h3>'+d.label+'</h3>'+
    '<div class="detail-row"><span>Kind</span><span>'+d.kind+'</span></div>'+
    '<div class="detail-row"><span>API Group</span><span>'+(d.apiGroup||'-')+'</span></div>'+
    '<div class="detail-row"><span>Version</span><span>'+(d.version||'-')+'</span></div>'+
    '<div class="detail-row"><span>Namespace</span><span>'+(d.namespace||'(cluster)')+'</span></div>'+
    '<div class="detail-row"><span>Sync</span><span class="sync-'+(d.syncStatus||'unknown').toLowerCase()+'">'+d.syncStatus+'</span></div>'+
    '<div class="detail-row"><span>Health</span><span class="health-'+(d.healthStatus||'unknown').toLowerCase()+'">'+d.healthStatus+'</span></div>'+
    '<div class="detail-row"><span>Parent</span><span>'+(d.parentApp||d.id)+'</span></div>'+
    '<button onclick="document.getElementById(\\'detail-panel\\').style.display=\\'none\\'">Close</button>';
}

// Tooltip
var tip=document.getElementById('tooltip');
cy.on('mouseover','node',function(e){var d=e.target.data();tip.textContent=d.kind+': '+d.label+' ['+d.healthStatus+']';tip.style.display='block'});
cy.on('mouseout','node',function(){tip.style.display='none'});
document.getElementById('cy').addEventListener('mousemove',function(e){tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY+12+'px'});

// Filtering (dropdowns + quick buttons, scoped to search results when highlight is on)
var unhealthyActive=false,oosActive=false;
function applyFilters(){
  var kf=document.getElementById('kindFilter').value;
  var nf=document.getElementById('nsFilter').value;
  var sf=document.getElementById('syncFilter').value;
  var hf=document.getElementById('healthFilter').value;
  var hasDropdown=kf||nf||sf||hf||unhealthyActive||oosActive;
  var hlOn=document.getElementById('sp-highlight').checked&&searchResults.length>0;
  var searchSet=null;
  if(hlOn){
    searchSet=new Set();
    searchResults.forEach(function(r){searchSet.add(r.id);searchSet.add(r.label)});
  }
  var hasF=hasDropdown||hlOn;
  cy.startBatch();
  cy.nodes().forEach(function(n){
    var d=n.data();
    var ok=true;
    if(hlOn){
      if(!searchSet.has(d.id)&&!searchSet.has(d.label))ok=false;
    }
    if(ok&&kf&&d.kind!==kf)ok=false;
    if(ok&&nf&&d.namespace!==nf)ok=false;
    if(ok&&sf&&d.syncStatus!==sf)ok=false;
    if(ok&&hf&&d.healthStatus!==hf)ok=false;
    if(ok&&unhealthyActive&&d.healthStatus==='Healthy')ok=false;
    if(ok&&oosActive&&d.syncStatus!=='OutOfSync')ok=false;
    if(hasF){n.toggleClass('dimmed',!ok);n.toggleClass('highlighted',ok)}
    else{n.removeClass('dimmed highlighted')}
  });
  cy.edges().forEach(function(e){
    var st=e.source(),tg=e.target();
    e.toggleClass('dimmed',hasF&&(st.hasClass('dimmed')||tg.hasClass('dimmed')));
  });
  cy.endBatch();
  updateStats();
}
['kindFilter','nsFilter','syncFilter','healthFilter'].forEach(function(id){document.getElementById(id).addEventListener('change',applyFilters)});

// Search — triggered by Enter or button, results shown in left panel
var searchResults=[];
var allResources=[];
// Build flat index of ALL resources (apps + children) for searching
G.nodes.forEach(function(n){allResources.push({id:n.data.id,label:n.data.label,kind:n.data.kind,apiGroup:n.data.apiGroup,namespace:n.data.namespace,syncStatus:n.data.syncStatus,healthStatus:n.data.healthStatus,parentApp:'',isApp:true})});
Object.keys(G.appChildren).forEach(function(pa){
  G.appChildren[pa].forEach(function(ch){
    if(ch.kind==='Application'||ch.kind==='ApplicationSet')return;
    allResources.push({id:ch.id,label:ch.label,kind:ch.kind,apiGroup:ch.apiGroup,namespace:ch.namespace,syncStatus:ch.syncStatus,healthStatus:ch.healthStatus,parentApp:pa,isApp:false});
  });
});

function doSearch(){
  var q=document.getElementById('search').value.trim().toLowerCase();
  if(!q){closeSearchPanel();return}
  searchResults=allResources.filter(function(r){
    return r.label.toLowerCase().indexOf(q)>=0||r.kind.toLowerCase().indexOf(q)>=0||(r.namespace||'').toLowerCase().indexOf(q)>=0||(r.apiGroup||'').toLowerCase().indexOf(q)>=0;
  });
  renderSearchPanel();
  if(document.getElementById('sp-highlight').checked)highlightSearchResults();
}
function renderSearchPanel(){
  var panel=document.getElementById('search-panel');
  panel.classList.add('open');
  document.getElementById('sp-count').textContent=searchResults.length+' result'+(searchResults.length!==1?'s':'');
  var grouped={};
  searchResults.forEach(function(r){
    var key=r.parentApp||r.label;
    if(!grouped[key])grouped[key]=[];
    grouped[key].push(r);
  });
  var html='';
  var parentKeys=Object.keys(grouped).sort();
  parentKeys.forEach(function(parent){
    var items=grouped[parent];
    html+='<div class="sp-group">'
      +'<div class="sp-group-header"><span class="sp-chevron">&#x25BC;</span>'
      +'<span class="sp-group-name" title="'+parent+'">'+parent+'</span>'
      +'<span class="sp-group-count">'+items.length+'</span></div>'
      +'<div class="sp-children">';
    items.forEach(function(r){
      html+='<div class="sp-item" data-idx="'+r.id+'" data-parent="'+r.parentApp+'" data-isapp="'+r.isApp+'">'
        +'<span class="sp-health-dot" style="background:'+hc(r.healthStatus)+'"></span>'
        +'<span class="sp-name" title="'+r.label+'">'+r.label+'</span>'
        +'<span class="sp-kind">'+r.kind+'</span></div>';
    });
    html+='</div></div>';
  });
  document.getElementById('sp-results').innerHTML=html;
  // Toggle group collapse
  document.querySelectorAll('.sp-group-header').forEach(function(hdr){
    hdr.addEventListener('click',function(){this.parentElement.classList.toggle('collapsed')});
  });
  // Click item to navigate on graph
  document.querySelectorAll('.sp-item').forEach(function(el){
    el.addEventListener('click',function(ev){
      ev.stopPropagation();
      var parentApp=this.dataset.parent;
      var isApp=this.dataset.isapp==='true';
      if(!isApp&&parentApp&&!expandedApps.has(parentApp))expandApp(parentApp);
      var node=null;
      if(isApp){node=cy.getElementById(this.dataset.idx)}
      else{var lbl=this.querySelector('.sp-name').title;cy.nodes().forEach(function(n){if(!node&&n.data('label')===lbl&&n.data('parentApp')===parentApp)node=n})}
      if(node&&node.length){
        cy.animate({center:{eles:node},zoom:cy.zoom()>1.5?cy.zoom():1.5},{duration:300});
        node.flashClass('highlighted',1500);
        showDetail(node.data());
      }
    });
  });
}
function expandSearchResultsOnGraph(){
  var parents=new Set();
  searchResults.forEach(function(r){if(r.parentApp)parents.add(r.parentApp)});
  parents.forEach(function(pa){if(!expandedApps.has(pa)&&cy.getElementById(pa).length)expandApp(pa)});
  if(document.getElementById('sp-highlight').checked)highlightSearchResults();
}
function highlightSearchResults(){applyFilters()}
function clearHighlights(){
  cy.startBatch();
  cy.nodes().removeClass('dimmed highlighted');
  cy.edges().removeClass('dimmed');
  cy.endBatch();
}
function closeSearchPanel(){
  document.getElementById('search-panel').classList.remove('open');
  searchResults=[];
  clearHighlights();
  updateStats();
}
document.getElementById('search').addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();doSearch()}});
document.getElementById('search-btn').addEventListener('click',doSearch);
document.getElementById('sp-close').addEventListener('click',closeSearchPanel);
document.getElementById('sp-highlight').addEventListener('change',function(){
  if(this.checked&&searchResults.length)highlightSearchResults();
  else clearHighlights();
});
document.getElementById('sp-expand-results').addEventListener('click',expandSearchResultsOnGraph);

document.getElementById('btn-unhealthy').addEventListener('click',function(){
  unhealthyActive=!unhealthyActive;this.classList.toggle('active',unhealthyActive);
  if(unhealthyActive){oosActive=false;document.getElementById('btn-outofsync').classList.remove('active')}
  applyFilters();
});
document.getElementById('btn-outofsync').addEventListener('click',function(){
  oosActive=!oosActive;this.classList.toggle('active',oosActive);
  if(oosActive){unhealthyActive=false;document.getElementById('btn-unhealthy').classList.remove('active')}
  applyFilters();
});

document.getElementById('expand-all').addEventListener('click',function(){G.nodes.forEach(function(n){if(n.data.isApp&&!expandedApps.has(n.data.id))expandApp(n.data.id)})});
document.getElementById('collapse-all').addEventListener('click',function(){[...expandedApps].forEach(collapseApp)});
document.getElementById('fit-btn').addEventListener('click',function(){cy.fit(null,30)});

document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){
    e.preventDefault();e.stopPropagation();
    document.getElementById('search').value='';
    document.querySelectorAll('#toolbar select').forEach(function(s){s.value=''});
    unhealthyActive=false;oosActive=false;
    document.getElementById('btn-unhealthy').classList.remove('active');
    document.getElementById('btn-outofsync').classList.remove('active');
    closeSearchPanel();
    applyFilters();
    document.getElementById('detail-panel').style.display='none';
    cy.nodes(':selected').unselect();
    document.activeElement.blur();
  }
},true);

// Drag selected nodes together using mousedown/mousemove on the container
var groupDragState=null;
var cyDiv=document.getElementById('cy');
cyDiv.addEventListener('mousedown',function(e){
  var sel=cy.nodes(':selected');
  if(sel.length<2)return;
  var pos=sel.map(function(n){return{node:n,x:n.position('x'),y:n.position('y')}});
  groupDragState={startX:e.clientX,startY:e.clientY,positions:pos,zoom:cy.zoom()};
});
cyDiv.addEventListener('mousemove',function(e){
  if(!groupDragState)return;
  if(!(e.buttons&1)){groupDragState=null;return}
  var dx=(e.clientX-groupDragState.startX)/groupDragState.zoom;
  var dy=(e.clientY-groupDragState.startY)/groupDragState.zoom;
  cy.startBatch();
  groupDragState.positions.forEach(function(p){
    p.node.position({x:p.x+dx,y:p.y+dy});
  });
  cy.endBatch();
});
cyDiv.addEventListener('mouseup',function(){groupDragState=null});

// Theme toggle (persisted in localStorage)
var isLight=localStorage.getItem('argocd-graph-theme')==='light';
function applyTheme(){
  document.body.classList.toggle('light',isLight);
  document.getElementById('theme-btn').textContent=isLight?'\\u2600':'\\u263E';
  var lbl=isLight?'#111':'#fff';
  var out=isLight?'#fff':'#111';
  var leafLbl=isLight?'#333':'#ccc';
  cy.startBatch();
  cy.style().selector('node[?isApp]').style({'color':lbl,'text-outline-color':out}).update();
  cy.style().selector('node[!isApp]').style({'color':leafLbl,'text-outline-color':out}).update();
  cy.style().selector('edge').style({'line-color':isLight?'#bbb':'#444','target-arrow-color':isLight?'#999':'#555'}).update();
  cy.endBatch();
}
applyTheme();
document.getElementById('theme-btn').addEventListener('click',function(){
  isLight=!isLight;
  localStorage.setItem('argocd-graph-theme',isLight?'light':'dark');
  applyTheme();
});

// Context menu
var ctxMenu=document.getElementById('ctx-menu');
var ctxTarget=null;
function showCtxMenu(x,y,node){
  ctxTarget=node;
  var sel=cy.nodes(':selected');
  var hasSelection=sel.length>1;
  var isApp=node&&node.data('isApp');
  var isExpanded=isApp&&expandedApps.has(node.data('id'));
  // Show/hide relevant items
  ctxMenu.querySelector('[data-action="compact"]').style.display=hasSelection?'':'none';
  ctxMenu.querySelector('[data-action="spread"]').style.display=hasSelection?'':'none';
  ctxMenu.querySelector('[data-action="circle"]').style.display=hasSelection?'':'none';
  ctxMenu.querySelector('[data-action="grid"]').style.display=hasSelection?'':'none';
  ctxMenu.querySelector('[data-action="expand"]').style.display=(isApp&&!isExpanded)?'':'none';
  ctxMenu.querySelector('[data-action="collapse"]').style.display=(isApp&&isExpanded)?'':'none';
  ctxMenu.querySelector('[data-action="select-children"]').style.display=isApp?'':'none';
  // Position and show
  ctxMenu.style.left=Math.min(x,window.innerWidth-200)+'px';
  ctxMenu.style.top=Math.min(y,window.innerHeight-300)+'px';
  ctxMenu.style.display='block';
}
function hideCtxMenu(){ctxMenu.style.display='none';ctxTarget=null}

cy.on('cxttap','node',function(e){
  e.originalEvent.preventDefault();
  showCtxMenu(e.originalEvent.clientX,e.originalEvent.clientY,e.target);
});
cy.on('cxttap',function(e){
  if(e.target===cy){
    var sel=cy.nodes(':selected');
    if(sel.length>1){
      showCtxMenu(e.originalEvent.clientX,e.originalEvent.clientY,null);
    }else{hideCtxMenu()}
  }
});
document.getElementById('cy').addEventListener('contextmenu',function(e){e.preventDefault()});
document.addEventListener('click',function(e){if(!ctxMenu.contains(e.target))hideCtxMenu()});

document.querySelectorAll('#ctx-menu .ctx-item').forEach(function(item){
  item.addEventListener('click',function(){
    var action=this.dataset.action;
    var sel=cy.nodes(':selected');
    var nodes=sel.length>1?sel:(ctxTarget?ctxTarget.collection():cy.collection());
    if(nodes.length===0){hideCtxMenu();return}

    if(action==='compact'){
      // Pack selected nodes tight around their centroid
      var cx=0,cy2=0;
      nodes.forEach(function(n){cx+=n.position('x');cy2+=n.position('y')});
      cx/=nodes.length;cy2/=nodes.length;
      var spacing=40;
      var cols=Math.ceil(Math.sqrt(nodes.length));
      cy.startBatch();
      nodes.forEach(function(n,i){
        var row=Math.floor(i/cols),col=i%cols;
        n.position({x:cx-(cols*spacing/2)+col*spacing,y:cy2-(Math.ceil(nodes.length/cols)*spacing/2)+row*spacing});
      });
      cy.endBatch();
    }
    else if(action==='spread'){
      // Spread out from centroid by 2x current spread
      var cx=0,cy2=0;
      nodes.forEach(function(n){cx+=n.position('x');cy2+=n.position('y')});
      cx/=nodes.length;cy2/=nodes.length;
      cy.startBatch();
      nodes.forEach(function(n){
        var dx=n.position('x')-cx;
        var dy=n.position('y')-cy2;
        n.position({x:cx+dx*2,y:cy2+dy*2});
      });
      cy.endBatch();
    }
    else if(action==='circle'){
      var cx=0,cy2=0;
      nodes.forEach(function(n){cx+=n.position('x');cy2+=n.position('y')});
      cx/=nodes.length;cy2/=nodes.length;
      var radius=Math.max(50,nodes.length*15);
      cy.startBatch();
      nodes.forEach(function(n,i){
        var angle=(2*Math.PI*i)/nodes.length-Math.PI/2;
        n.position({x:cx+radius*Math.cos(angle),y:cy2+radius*Math.sin(angle)});
      });
      cy.endBatch();
    }
    else if(action==='grid'){
      var cx=0,cy2=0;
      nodes.forEach(function(n){cx+=n.position('x');cy2+=n.position('y')});
      cx/=nodes.length;cy2/=nodes.length;
      var spacing=60;
      var cols=Math.ceil(Math.sqrt(nodes.length));
      cy.startBatch();
      nodes.forEach(function(n,i){
        var row=Math.floor(i/cols),col=i%cols;
        n.position({x:cx-(cols*spacing/2)+col*spacing,y:cy2-(Math.ceil(nodes.length/cols)*spacing/2)+row*spacing});
      });
      cy.endBatch();
    }
    else if(action==='select-children'){
      if(ctxTarget&&ctxTarget.data('isApp')){
        var appId=ctxTarget.data('id');
        if(!expandedApps.has(appId))expandApp(appId);
        cy.nodes().forEach(function(n){if(n.data('parentApp')===appId)n.select()});
      }
    }
    else if(action==='select-siblings'){
      var pa=ctxTarget?ctxTarget.data('parentApp'):'';
      if(pa){cy.nodes().forEach(function(n){if(n.data('parentApp')===pa)n.select()})}
    }
    else if(action==='expand'&&ctxTarget&&ctxTarget.data('isApp')){
      expandApp(ctxTarget.data('id'));
    }
    else if(action==='collapse'&&ctxTarget&&ctxTarget.data('isApp')){
      collapseApp(ctxTarget.data('id'));
    }
    hideCtxMenu();
  });
});

function updateStats(){
  var vis=cy.nodes().filter(function(n){return !n.hasClass('dimmed')}).length;
  var tot=cy.nodes().length;
  document.getElementById('stats-display').textContent='Showing '+vis+' / '+tot+' nodes | '+G.stats.totalApps+' apps | '+G.stats.totalLeaves+' leaves';
}
updateStats();
"""


def _is_app_resource(r):
    kind = r.get("kind", "")
    group = r.get("group", "")
    if kind == "Application" and (group == "argoproj.io" or "argocd" in group.lower()):
        return True
    if kind == "ApplicationSet" and group == "argoproj.io":
        return True
    return False


def build_graph_data(resources, root_app=None):
    app_names = set()
    apps = []
    leaves = []

    for r in resources:
        if _is_app_resource(r):
            apps.append(r)
            app_names.add(r["name"])
        else:
            leaves.append(r)

    parent_apps = {r.get("parentApp") for r in resources if r.get("parentApp")}
    root_candidates = parent_apps - app_names

    if root_app:
        root_name = root_app
    elif len(root_candidates) == 1:
        root_name = root_candidates.pop()
    elif len(root_candidates) == 0:
        print(
            "Error: no root app detected (all parentApps exist as resources)",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(
            f"Error: multiple root candidates detected: {sorted(root_candidates)}. Use --root-app to pick one.",
            file=sys.stderr,
        )
        sys.exit(1)

    children_count = {}
    for r in resources:
        pa = r.get("parentApp")
        if pa:
            children_count[pa] = children_count.get(pa, 0) + 1

    nodes = []
    edges = []

    root_node = {
        "data": {
            "id": root_name,
            "label": root_name,
            "kind": "Application",
            "apiGroup": "argoproj.io",
            "version": "v1alpha1",
            "namespace": "",
            "syncStatus": "Synced",
            "healthStatus": "Healthy",
            "isApp": True,
            "isRoot": True,
            "childCount": children_count.get(root_name, 0),
        }
    }
    nodes.append(root_node)

    for r in apps:
        node = {
            "data": {
                "id": r["name"],
                "label": r["name"],
                "kind": r.get("kind", ""),
                "apiGroup": r.get("group", ""),
                "version": r.get("version", ""),
                "namespace": r.get("namespace", ""),
                "syncStatus": r.get("syncStatus", ""),
                "healthStatus": r.get("healthStatus", ""),
                "isApp": True,
                "isRoot": False,
                "childCount": children_count.get(r["name"], 0),
            }
        }
        nodes.append(node)

        pa = r.get("parentApp")
        if pa:
            edges.append({"data": {"source": pa, "target": r["name"]}})

    app_children = {}
    for r in resources:
        pa = r.get("parentApp")
        if not pa:
            continue
        entry = {
            "id": f"{r.get('group', '')}/{r.get('kind', '')}/{r.get('namespace', '')}/{r['name']}",
            "label": r["name"],
            "kind": r.get("kind", ""),
            "apiGroup": r.get("group", ""),
            "version": r.get("version", ""),
            "namespace": r.get("namespace", ""),
            "syncStatus": r.get("syncStatus", ""),
            "healthStatus": r.get("healthStatus", ""),
            "parentApp": pa,
        }
        app_children.setdefault(pa, []).append(entry)

    all_kinds = sorted({r.get("kind", "") for r in resources} - {""})
    all_ns = sorted({r.get("namespace", "") for r in resources} - {""})
    all_sync = sorted({r.get("syncStatus", "") for r in resources} - {""})
    all_health = sorted({r.get("healthStatus", "") for r in resources} - {""})

    stats = {
        "totalResources": len(resources),
        "totalApps": len(apps) + 1,
        "totalLeaves": len(leaves),
        "kinds": all_kinds,
        "namespaces": all_ns,
        "syncStatuses": all_sync,
        "healthStatuses": all_health,
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "appChildren": app_children,
        "stats": stats,
        "rootApp": root_name,
    }


def generate_html(graph_data, title):
    data_json = json.dumps(graph_data, separators=(",", ":"))
    data_json = data_json.replace("</", "<\\/")
    js = JS_TEMPLATE.replace("__GRAPH_DATA__", data_json)
    html = HTML_TEMPLATE.replace("__JS_CODE__", js)
    html = html.replace("__TITLE__", title)
    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generate ArgoCD resource graph visualization"
    )
    parser.add_argument(
        "--root-app", help="Root application name (auto-detected if omitted)"
    )
    parser.add_argument(
        "--output", default="/tmp/argocd-graph.html", help="Output HTML file path"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Don't auto-open browser"
    )
    parser.add_argument("--title", default="ArgoCD Resource Graph", help="Page title")
    args = parser.parse_args()

    if sys.stdin.isatty():
        print(
            "Error: pipe JSON from list-argocd-resources.py --recursive --output json",
            file=sys.stderr,
        )
        sys.exit(1)

    resources = json.loads(sys.stdin.read())
    graph_data = build_graph_data(resources, args.root_app)
    html = generate_html(graph_data, args.title)

    output_path = os.path.abspath(args.output)
    with open(output_path, "w") as f:
        f.write(html)
    print(f"Graph written to {output_path}", file=sys.stderr)
    print(
        f"Apps: {graph_data['stats']['totalApps']}, "
        f"Leaves: {graph_data['stats']['totalLeaves']}, "
        f"Total: {graph_data['stats']['totalResources']}",
        file=sys.stderr,
    )

    if not args.no_open:
        webbrowser.open(f"file://{output_path}")


if __name__ == "__main__":
    main()
