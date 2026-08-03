function downloadDataUrl(dataUrl,filename){const link=document.createElement('a');link.href=dataUrl;link.download=filename;document.body.append(link);link.click();link.remove()}
function downloadBlob(blob,filename){const url=URL.createObjectURL(blob);downloadDataUrl(url,filename);setTimeout(()=>URL.revokeObjectURL(url),1000)}
function canvasFilename(canvas){return `${canvas.id||'chart'}.png`}
function saveCanvas(canvas){downloadDataUrl(canvas.toDataURL('image/png'),canvasFilename(canvas))}
async function tradeChartDataUrl(width=1600,height=null){const plot=document.querySelector('#trade-plot');if(!plot||!plot.data?.length)return null;return Plotly.toImage(plot,{format:'png',width,height:height||Math.max(700,plot.clientHeight*2),scale:1})}
async function saveTradeChart(){const url=await tradeChartDataUrl();if(url)downloadDataUrl(url,`trade-${state.selectedTradeData?.position_id??'chart'}.png`)}
function loadExportImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=url})}
async function saveAllCharts(){
  // Render each page while visible; hidden responsive canvases otherwise export blank.
  const originalPage=state.page,assets=[];
  for(const page of ['overview','robustness','trades']){
    state.page=page;document.querySelectorAll('[data-page-content]').forEach(node=>node.classList.toggle('hidden',node.dataset.pageContent!==page));
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    if(page==='overview'){drawLine();drawPips();drawBars()}if(page==='robustness')renderStability(state.data.windows[state.selected]);if(page==='trades'){drawTradeDistribution(allTrades());drawTradeCumulative(allTrades())}
    await new Promise(resolve=>requestAnimationFrame(resolve));
    for(const canvas of document.querySelectorAll(`[data-page-content="${page}"] canvas[id]`)){const image=await loadExportImage(canvas.toDataURL('image/png'));assets.push({name:canvas.id,image,width:image.naturalWidth,height:image.naturalHeight})}
  }
  state.page=originalPage;document.querySelectorAll('[data-page-content]').forEach(node=>node.classList.toggle('hidden',node.dataset.pageContent!==originalPage));
  const tradeUrl=await tradeChartDataUrl();
  if(tradeUrl){const image=await loadExportImage(tradeUrl);assets.push({name:'Trade chart',image,width:image.naturalWidth,height:image.naturalHeight})}
  if(!assets.length)return;
  const targetWidth=1600,gap=48,labelHeight=42;
  const scaled=assets.map(asset=>{const scale=targetWidth/asset.width;return{...asset,drawWidth:targetWidth,drawHeight:asset.height*scale}});
  const height=Math.ceil(scaled.reduce((total,asset)=>total+asset.drawHeight+labelHeight+gap,24));
  const output=document.createElement('canvas');output.width=targetWidth;output.height=height;
  const context=output.getContext('2d');context.fillStyle=themeColor('--chart-bg');context.fillRect(0,0,targetWidth,height);context.fillStyle=themeColor('--chart-text');context.font='600 24px system-ui';
  let y=24;for(const asset of scaled){context.fillText(asset.name,20,y+27);y+=labelHeight;context.drawImage(asset.image,0,y,asset.drawWidth,asset.drawHeight);y+=asset.drawHeight+gap}
  downloadDataUrl(output.toDataURL('image/png'),'trading-wfo-all-charts.png');
}

function dataUrlBytes(url){const binary=atob(url.split(',')[1]),bytes=new Uint8Array(binary.length);for(let index=0;index<binary.length;index++)bytes[index]=binary.charCodeAt(index);return bytes}
const crcTable=(()=>{const table=new Uint32Array(256);for(let n=0;n<256;n++){let value=n;for(let bit=0;bit<8;bit++)value=(value&1)?0xedb88320^(value>>>1):value>>>1;table[n]=value>>>0}return table})();
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes)crc=crcTable[(crc^byte)&255]^(crc>>>8);return(crc^0xffffffff)>>>0}
function joinBytes(parts){const size=parts.reduce((sum,part)=>sum+part.length,0),output=new Uint8Array(size);let offset=0;for(const part of parts){output.set(part,offset);offset+=part.length}return output}
function zipStoredFiles(files){
  const encoder=new TextEncoder(),locals=[],centrals=[];let offset=0;
  for(const file of files){const name=encoder.encode(file.name),data=file.bytes,crc=crc32(data);const local=new Uint8Array(30+name.length),lv=new DataView(local.buffer);lv.setUint32(0,0x04034b50,true);lv.setUint16(4,20,true);lv.setUint32(14,crc,true);lv.setUint32(18,data.length,true);lv.setUint32(22,data.length,true);lv.setUint16(26,name.length,true);local.set(name,30);locals.push(local,data);const central=new Uint8Array(46+name.length),cv=new DataView(central.buffer);cv.setUint32(0,0x02014b50,true);cv.setUint16(4,20,true);cv.setUint16(6,20,true);cv.setUint32(16,crc,true);cv.setUint32(20,data.length,true);cv.setUint32(24,data.length,true);cv.setUint16(28,name.length,true);cv.setUint32(42,offset,true);central.set(name,46);centrals.push(central);offset+=local.length+data.length}
  const centralSize=centrals.reduce((sum,part)=>sum+part.length,0),end=new Uint8Array(22),view=new DataView(end.buffer);view.setUint32(0,0x06054b50,true);view.setUint16(8,files.length,true);view.setUint16(10,files.length,true);view.setUint32(12,centralSize,true);view.setUint32(16,offset,true);return joinBytes([...locals,...centrals,end])
}
async function saveAllTrades(){
  const button=document.querySelector('#save-all-trades'),message=document.querySelector('#trade-chart-message'),trades=allTrades();if(!trades.length||!state.chartConfig?.market_configured)return;
  const original={selectedTrade:state.selectedTrade,selectedTradeData:state.selectedTradeData,timeframes:[...state.chartTimeframes],series:[...state.chartSeries]};const files=[];button.disabled=true;
  try{state.chartTimeframes=[state.chartConfig.base_timeframe_seconds];state.chartSeries=[];for(let index=0;index<trades.length;index++){const trade=trades[index];state.selectedTradeData=trade;message.textContent=`Exporting trade ${index+1} / ${trades.length}…`;await renderTradeChartV2();const url=await tradeChartDataUrl(1400,760);files.push({name:`window-${trade._window+1}_trade-${trade.position_id??index+1}.png`,bytes:dataUrlBytes(url)});await new Promise(resolve=>setTimeout(resolve,0))}message.textContent='Creating ZIP…';downloadBlob(new Blob([zipStoredFiles(files)],{type:'application/zip'}),'trading-wfo-all-trades.zip')}
  finally{state.selectedTrade=original.selectedTrade;state.selectedTradeData=original.selectedTradeData;state.chartTimeframes=original.timeframes;state.chartSeries=original.series;button.disabled=false;if(state.selectedTradeData){renderActiveSeries();await renderTradeChartV2()}else message.textContent=''}
}
function autoscaleTradeChart(){const plot=document.querySelector('#trade-plot');if(!plot?.layout)return;const update={};for(const key of Object.keys(plot.layout)){if(/^[xy]axis\d*$/.test(key)){update[`${key}.autorange`]=true;update[`${key}.fixedrange`]=false}}return Plotly.relayout(plot,update)}
function installTradeContextMenu(){const plot=document.querySelector('#trade-plot'),menu=document.createElement('div');menu.id='trade-chart-context-menu';menu.className='trade-context-menu hidden';menu.innerHTML='<button type="button" data-chart-command="save">Save this trade PNG</button><button type="button" data-chart-command="autoscale">Autoscale all axes</button>';document.body.append(menu);plot.addEventListener('contextmenu',event=>{event.preventDefault();menu.style.left=`${Math.min(event.clientX,window.innerWidth-220)}px`;menu.style.top=`${Math.min(event.clientY,window.innerHeight-100)}px`;menu.classList.remove('hidden')});menu.addEventListener('click',event=>{const command=event.target.dataset.chartCommand;if(command==='save')saveTradeChart();if(command==='autoscale')autoscaleTradeChart();menu.classList.add('hidden')});document.addEventListener('click',event=>{if(!menu.contains(event.target))menu.classList.add('hidden')});window.addEventListener('scroll',()=>menu.classList.add('hidden'),true)}
function installChartExportButtons(){document.querySelectorAll('.panel').forEach(panel=>{const canvas=panel.querySelector('canvas[id]'),heading=panel.querySelector('.panel-heading');if(!canvas||!heading||heading.querySelector('.save-canvas-chart'))return;const button=el('button','Save PNG','control-button save-canvas-chart');button.type='button';button.addEventListener('click',()=>saveCanvas(canvas));heading.append(button)});document.querySelector('#save-all-charts')?.addEventListener('click',saveAllCharts);document.querySelector('#save-trade-chart')?.addEventListener('click',saveTradeChart);document.querySelector('#save-all-trades')?.addEventListener('click',saveAllTrades);installTradeContextMenu()}
installChartExportButtons();
