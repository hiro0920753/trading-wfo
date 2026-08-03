/* Interactive trade chart kept separate from the dashboard summary charts. */
async function renderTradeChartV2(){
  const trade=state.selectedTradeData;
  if(!trade||!state.chartConfig?.market_configured)return;
  const plot=document.querySelector('#trade-plot');
  const message=document.querySelector('#trade-chart-message');
  message.textContent='Loading chart…';
  try{
    const range=tradeRange();
    const marketSets=await Promise.all(state.chartTimeframes.map(seconds=>fetchChartJson(`/api/chart/market?start=${range.start}&end=${range.end}&timeframe=${seconds}`)));
    const needsLogs=state.chartSeries.some(series=>series.source==='log');
    const logs=needsLogs?await fetchChartJson(`/api/chart/logs?start=${range.start}&end=${range.end}`):{records:[]};
    const colors={
      panel:themeColor('--chart-bg'),text:themeColor('--chart-text'),grid:themeColor('--chart-grid'),
      bid:themeColor('--chart-bid'),ask:themeColor('--chart-ask'),open:themeColor('--chart-open'),close:themeColor('--chart-close'),
      up:themeColor('--chart-up'),down:themeColor('--chart-down'),entry:themeColor('--chart-entry'),exit:themeColor('--chart-exit')
    };
    const traces=[];
    const paneLabels=['Market prices',...state.chartTimeframes.map(seconds=>`${timeframeLabel(seconds)} candles`)];
    state.chartSeries.filter(series=>series.pane==='pane').forEach(series=>paneLabels.push(`${series.source}: ${series.column}`));
    const paneCount=paneLabels.length;
    const gap=.035,usable=1-gap*(paneCount-1),height=usable/paneCount;
    const hoverValues=state.chartHoverValues;
    const layout={
      paper_bgcolor:colors.panel,plot_bgcolor:colors.panel,font:{color:colors.text,size:15},
      margin:{l:78,r:35,t:40,b:55},height:Math.max(620,270*paneCount),
      hovermode:hoverValues?'x unified':false,hoverlabel:{bgcolor:colors.panel,bordercolor:colors.grid,font:{color:colors.text,size:14}},
      dragmode:'pan',showlegend:true,legend:{orientation:'h',y:1.025,x:0,font:{size:14}},shapes:[],annotations:[]
    };
    const sourceRows=marketSets[0]?.records||[];
    const sourceX=sourceRows.map(row=>row.time);
    const lineAxis={xaxis:'x',yaxis:'y'};
    traces.push(
      {type:'scattergl',mode:'lines',name:'Bid',x:sourceX,y:sourceRows.map(row=>row.bid),...lineAxis,line:{color:colors.bid,width:1.8}},
      {type:'scattergl',mode:'lines',name:'Ask',x:sourceX,y:sourceRows.map(row=>row.ask),...lineAxis,line:{color:colors.ask,width:1.8}},
      {type:'scattergl',mode:'lines',name:'Open',x:sourceX,y:sourceRows.map(row=>row.open),...lineAxis,line:{color:colors.open,width:1.4,dash:'dot'}},
      {type:'scatter',mode:'markers',name:'ENTRY',x:[new Date(chartTime(trade.time)).toISOString()],y:[trade.entry_price],...lineAxis,marker:{symbol:trade.side==='short'?'triangle-down':'triangle-up',size:18,color:colors.entry,line:{color:colors.panel,width:2}}},
      {type:'scatter',mode:'markers',name:'CLOSE',x:[new Date(chartTime(trade.exit_time)).toISOString()],y:[trade.exit_price],...lineAxis,marker:{symbol:'x',size:17,color:colors.exit,line:{color:colors.exit,width:3}}}
    );
    layout.shapes.push({type:'rect',xref:'x',yref:'y domain',x0:new Date(chartTime(trade.time)).toISOString(),x1:new Date(chartTime(trade.exit_time)).toISOString(),y0:0,y1:1,fillcolor:trade.side==='short'?'rgba(0,163,224,.08)':'rgba(123,97,255,.08)',line:{width:0},layer:'below'});
    layout.shapes.push(
      {type:'line',xref:'x',yref:'paper',x0:new Date(chartTime(trade.time)).toISOString(),x1:new Date(chartTime(trade.time)).toISOString(),y0:0,y1:1,line:{color:colors.entry,width:2,dash:'dot'}},
      {type:'line',xref:'x',yref:'paper',x0:new Date(chartTime(trade.exit_time)).toISOString(),x1:new Date(chartTime(trade.exit_time)).toISOString(),y0:0,y1:1,line:{color:colors.exit,width:2,dash:'dot'}}
    );
    layout.annotations.push(
      {xref:'x',yref:'y domain',x:new Date(chartTime(trade.time)).toISOString(),y:.98,text:'ENTRY',showarrow:false,yanchor:'top',font:{color:colors.entry,size:14}},
      {xref:'x',yref:'y domain',x:new Date(chartTime(trade.exit_time)).toISOString(),y:.98,text:'CLOSE',showarrow:false,yanchor:'top',font:{color:colors.exit,size:14}}
    );
    let pane=1;
    marketSets.forEach(payload=>{
      const rows=payload.records||[],x=rows.map(row=>row.time),xaxis=axisRef('x',pane),yaxis=axisRef('y',pane);
      traces.push({type:'candlestick',name:`OHLC ${timeframeLabel(payload.timeframe_seconds)}`,x,open:rows.map(row=>row.open),high:rows.map(row=>row.high),low:rows.map(row=>row.low),close:rows.map(row=>row.close),xaxis,yaxis,increasing:{line:{color:colors.up},fillcolor:colors.up},decreasing:{line:{color:colors.down},fillcolor:colors.down}});
      pane++;
    });
    for(const series of state.chartSeries){
      const records=series.source==='log'?logs.records:sourceRows;
      const targetPane=series.pane==='overlay'?0:pane++;
      traces.push({type:'scattergl',mode:'lines',name:`${series.source}: ${series.column}`,x:records.map(row=>row.time),y:records.map(row=>row[series.column]),xaxis:axisRef('x',targetPane),yaxis:axisRef('y',targetPane),line:{width:2}});
    }
    for(let index=0;index<paneCount;index++){
      const top=1-index*(height+gap),bottom=top-height,xName=axisName('xaxis',index),yName=axisName('yaxis',index);
      layout[xName]={domain:[0,1],anchor:axisRef('y',index),matches:index?'x':undefined,rangeslider:{visible:false},showticklabels:index===paneCount-1,gridcolor:colors.grid,linecolor:colors.grid,tickfont:{size:14,color:colors.text},zeroline:false,title:index===paneCount-1?{text:'Date / time',font:{size:15,color:colors.text}}:undefined};
      layout[yName]={domain:[bottom,top],anchor:axisRef('x',index),gridcolor:colors.grid,linecolor:colors.grid,tickfont:{size:14,color:colors.text},zeroline:false,title:{text:paneLabels[index]||'Value',font:{size:15,color:colors.text}}};
    }
    await Plotly.newPlot(plot,traces,layout,{responsive:true,scrollZoom:false,displaylogo:false,toImageButtonOptions:{format:'png',filename:`trade-${trade.position_id??'chart'}`}});
    message.textContent=`${sourceRows.length} source bars · ${paneCount} panes`;
  }catch(error){message.textContent=error.message;Plotly.purge(plot)}
}

// app.js resolves this binding when controls or a trade selection request a redraw.
renderTradeChart=renderTradeChartV2;
