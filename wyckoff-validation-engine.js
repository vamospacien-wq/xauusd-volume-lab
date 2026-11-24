/* Contextual Wyckoff validation research. Confirmation-aware; heuristic only. */
(function(root){"use strict";
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:0;
const median=a=>{const x=a.filter(Number.isFinite).sort((p,q)=>p-q);if(!x.length)return 0;const m=x.length>>1;return x.length%2?x[m]:(x[m-1]+x[m])/2};
function atr(b,i,n){let a=[];for(let k=Math.max(1,i-n+1);k<=i;k++){let x=b[k],p=b[k-1];a.push(Math.max(x.high-x.low,Math.abs(x.high-p.close),Math.abs(x.low-p.close)))}return mean(a)}
function analyze(bars,opt){opt=opt||{};let n=Math.max(20,Math.min(120,Math.floor(+opt.rangeWindow||40))),vm=Math.max(1,+opt.volumeMultiple||1.5),raw=[];
for(let i=n+20;i<bars.length-15;i++){let w=bars.slice(i-n,i),hi=Math.max(...w.map(x=>x.high)),lo=Math.min(...w.map(x=>x.low)),width=hi-lo,a=atr(bars,i,14);if(!(a>0)||width<=0||width>a*8)continue;
if(Math.abs(w[w.length-1].close-w[0].open)/width>.55)continue;
let prior=bars.slice(Math.max(0,i-2*n),i-n),pm=prior.length?prior[prior.length-1].close-prior[0].open:0,bias=pm>a*2?"after_advance":pm< -a*2?"after_decline":"neutral";
let b=bars[i],vmed=median(w.slice(-20).map(x=>+x.volume||0)),vr=vmed>0?(+b.volume||0)/vmed:0,range=Math.max(1e-12,b.high-b.low),be=Math.abs(b.close-b.open)/range,lower=(Math.min(b.open,b.close)-b.low)/range,upper=(b.high-Math.max(b.open,b.close))/range;
let spring=b.low<lo-a*.05&&b.close>lo&&b.close<(hi+lo)/2,utad=b.high>hi+a*.05&&b.close<hi&&b.close>(hi+lo)/2;
if(!spring&&!utad)continue;
let confirmIndex=-1,confirmDir=spring?1:-1;
for(let k=i+1;k<=i+3;k++){let x=bars[k];if(spring&&x.close>lo+width*.25){confirmIndex=k;break}if(utad&&x.close<hi-width*.25){confirmIndex=k;break}}
if(confirmIndex<0||vr<vm)continue;
let cb=bars[confirmIndex],ca=atr(bars,confirmIndex,14);if(!(ca>0))continue;
let forward={};for(let h of [1,3,5,10]){let f=bars.slice(confirmIndex+1,confirmIndex+h+1);if(f.length<h){forward[h]=null;continue}let end=f[h-1].close,mfe=confirmDir===1?Math.max(...f.map(x=>x.high))-cb.close:cb.close-Math.min(...f.map(x=>x.low)),mae=confirmDir===1?cb.close-Math.min(...f.map(x=>x.low)):Math.max(...f.map(x=>x.high))-cb.close;forward[h]={directionalClose:(end-cb.close)*confirmDir/ca,mfe:mfe/ca,mae:mae/ca}}
let effort=vr>=vm&&be<=.35,score=Math.min(100,Math.round(Math.min(vr/vm,2)*20+(effort?25:0)+25+15+(bias!=="neutral"?5:0)));
raw.push({index:i,confirmationIndex:confirmIndex,time:b.time,confirmationTime:cb.time,high:hi,low:lo,bias,classification:spring?"Posible acumulación":"Posible distribución",event:spring?"Spring + recuperación confirmada":"UTAD + rechazo confirmado",confidence:"Media",volumeRatio:vr,bodyEfficiency:be,lowerWick:lower,upperWick:upper,effortNoResult:effort,score,forward})}
let ranges=[];for(let r of raw){let p=ranges[ranges.length-1];if(p&&r.index-p.lastIndex<Math.max(5,Math.floor(n/3))){if(r.score>p.score){r.firstIndex=p.firstIndex;r.lastIndex=r.index;ranges[ranges.length-1]=r}else p.lastIndex=r.index}else{r.firstIndex=r.index;r.lastIndex=r.index;ranges.push(r)}}
let outcomes={};for(let h of [1,3,5,10]){let q=ranges.map(x=>x.forward[h]).filter(Boolean);outcomes[h]={samples:q.length,positiveCloseRate:q.length?100*q.filter(x=>x.directionalClose>0).length/q.length:null,meanDirectionalATR:mean(q.map(x=>x.directionalClose)),meanMFE:mean(q.map(x=>x.mfe)),meanMAE:mean(q.map(x=>x.mae))}}
return {ranges,events:ranges,outcomes,summary:{bars:bars.length,rawWindows:raw.length,ranges:ranges.length,accumulation:ranges.filter(x=>x.classification.includes("acumulación")).length,distribution:ranges.filter(x=>x.classification.includes("distribución")).length,indeterminate:0,springs:ranges.filter(x=>x.event.includes("Spring")).length,utads:ranges.filter(x=>x.event.includes("UTAD")).length,effortNoResult:ranges.filter(x=>x.effortNoResult).length},note:"Eventos confirmados usando hasta tres velas posteriores. Las métricas empiezan después de la vela de confirmación para evitar usar esa misma información como rendimiento. Sin costes, slippage ni reglas de ejecución."}}
root.WyckoffValidationResearch={analyze};
})(typeof window!=="undefined"?window:globalThis);
