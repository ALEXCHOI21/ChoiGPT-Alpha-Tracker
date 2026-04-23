document.addEventListener('DOMContentLoaded', () => {
    initAlphaTracker();
});

async function initAlphaTracker() {
    console.log("Alpha Tracker Engine Init...");
    fetchData();
    setInterval(fetchData, 60000); // 1분마다 갱신
}

async function fetchData() {
    try {
        // 캐시 방지를 위해 타임스탬프 파라미터(t=...) 추가
        const response = await fetch('data/alpha_live.json?t=' + Date.now());
        if (!response.ok) throw new Error('데이터 파일을 찾을 수 없습니다.');
        const data = await response.json();
        
        updateUI(data);
    } catch (error) {
        console.error("Alpha Error:", error);
        // 에러 발생 시 안내 메시지 표시
        document.getElementById('alphaTableBody').innerHTML = `
            <tr>
                <td colspan="6" style="text-align:center; color:var(--danger); padding: 2rem;">
                    ⚠️ 로컬 보안 정책으로 인해 데이터를 불러올 수 없습니다.<br>
                    <code style="display:block; margin-top:10px; color:var(--text-sub)">python -m http.server</code>
                    터미널에서 위 명령어를 실행 후 접속하시거나, 서버 환경에서 구동하십시오.
                </td>
            </tr>`;
    }
}

function updateUI(data) {
    // 0. My Wallet (Real Data)
    if (data.wallet && data.wallet.total_usdt !== undefined) {
        document.getElementById('walletTotal').innerText = '$' + data.wallet.total_usdt.toLocaleString();
        document.getElementById('walletFree').innerText = '$' + data.wallet.free_usdt.toLocaleString();
        
        const posContainer = document.getElementById('walletPositions');
        if (data.wallet.active_positions && data.wallet.active_positions.length > 0) {
            posContainer.innerHTML = '';
            data.wallet.active_positions.forEach(p => {
                const isProfit = p.unrealizedPnl >= 0;
                const color = isProfit ? 'var(--success)' : 'var(--danger)';
                const div = document.createElement('div');
                div.style = `padding: 0.6rem 1rem; background: rgba(255,255,255,0.05); border-radius: 8px; border-left: 3px solid ${color}; display: flex; flex-direction: column; gap: 0.2rem; min-width: 140px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);`;
                div.innerHTML = `
                    <div style="font-weight: 700; font-size: 0.9rem; display: flex; justify-content: space-between; align-items: center;">
                        ${p.symbol} 
                        <span style="color:${color}; font-size: 0.75rem; border: 1px solid ${color}; padding: 1px 4px; border-radius: 4px;">${p.side}</span>
                    </div>
                    <div style="font-size: 0.8rem; color: var(--text-sub);">Size: ${p.size}</div>
                    <div style="font-size: 0.95rem; font-weight: 800; color: ${color}; margin-top: 4px;">${isProfit ? '+' : ''}${p.unrealizedPnl.toFixed(2)} USDT</div>
                `;
                posContainer.appendChild(div);
            });
        } else {
            posContainer.innerHTML = '<span style="color: var(--text-sub); font-size: 0.9rem;">현재 보유 중인 포지션이 없습니다.</span>';
        }
    }

    // 1. Last Updated
    document.getElementById('lastUpdated').innerText = `SYNCED AT ${data.last_updated}`;

    // 2. Market Health
    const fng = data.market_health.fear_greed;
    const fgValue = document.getElementById('fgValue');
    fgValue.innerText = fng.value;
    fgValue.style.color = getFGColor(fng.value);
    document.getElementById('fgLabel').innerText = fng.classification;

    const kp = data.market_health.kimchi_premium;
    const kpValue = document.getElementById('kpValue');
    kpValue.innerText = `${kp.premium_pct > 0 ? '+' : ''}${kp.premium_pct}%`;
    kpValue.style.color = kp.premium_pct > 3 ? 'var(--danger)' : kp.premium_pct < 0 ? 'var(--success)' : 'var(--warning)';

    // 3. Accumulation Gems Table
    const gemsTableBody = document.getElementById('gemsTableBody');
    if (gemsTableBody && data.accumulation_gems) {
        gemsTableBody.innerHTML = '';
        data.accumulation_gems.forEach(gem => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <div class="symbol-cell">
                        <img src="https://bin.bnbstatic.com/static/images/common/favicon.ico" width="20" style="filter:grayscale(1) brightness(2);">
                        ${gem.symbol}
                    </div>
                </td>
                <td class="mono">${gem.price < 0.01 ? gem.price.toFixed(8) : gem.price.toLocaleString()}</td>
                <td style="color: ${gem.change >= 0 ? 'var(--success)' : 'var(--danger)'}; font-weight: 700;">
                    ${gem.change > 0 ? '+' : ''}${gem.change.toFixed(2)}%
                </td>
                <td style="font-weight: 800; color: var(--accent-primary);">${gem.score} CP</td>
                <td>
                    <div style="font-size: 0.8rem; font-weight: 600; color: var(--accent-secondary);">
                        ${gem.analogy.case_name} (${gem.analogy.similarity}%)
                    </div>
                    <div style="font-size: 0.7rem; color: var(--text-sub);">${gem.analogy.description}</div>
                </td>
                <td>
                    <span class="badge badge-warning">${gem.status}</span>
                </td>
            `;
            gemsTableBody.appendChild(row);
        });
    }

    // 4. Alpha Signals Table (Trending)
    const tableBody = document.getElementById('alphaTableBody');
    tableBody.innerHTML = ''; 

    data.alpha_signals.forEach(signal => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <div class="symbol-cell">
                    <img src="https://bin.bnbstatic.com/static/images/common/favicon.ico" width="20" style="filter:grayscale(1) brightness(2);">
                    ${signal.symbol}
                </div>
            </td>
            <td class="mono">${signal.price < 0.01 ? signal.price.toFixed(8) : signal.price.toLocaleString()}</td>
            <td style="color: ${signal.change >= 0 ? 'var(--success)' : 'var(--danger)'}; font-weight: 700;">
                ${signal.change > 0 ? '+' : ''}${signal.change.toFixed(2)}%
            </td>
            <td>${signal.volume_24h}M</td>
            <td style="font-weight: 800; color: var(--accent-primary);">${signal.score ? signal.score : '--'}</td>
            <td>
                <span class="badge ${getBadgeClass(signal.status)}">${signal.status}</span>
            </td>
        `;
        tableBody.appendChild(row);
    });

    // 5. Trending Top 3 (Based on Gems if possible, otherwise trending)
    const trendingList = document.getElementById('trendingList');
    trendingList.innerHTML = '';
    const topGems = data.accumulation_gems ? data.accumulation_gems.slice(0, 3) : data.alpha_signals.slice(0, 3);
    topGems.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'trending-item';
        div.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="rank">${index + 1}</span>
                <span style="font-weight: 600;">${item.symbol}</span>
            </div>
            <span style="color: var(--success); font-weight: 800;">SIMIL. ${item.analogy ? item.analogy.similarity : '--'}%</span>
        `;
        trendingList.appendChild(div);
    });

    // 6. DeFi Hot Issues (Now showing Social Market Info)
    const defiList = document.getElementById('defiList');
    defiList.innerHTML = '';
    data.defi_issues.forEach(issue => {
        const div = document.createElement('div');
        div.className = 'trending-item';
        div.innerHTML = `
            <div style="font-size: 0.85rem; color: var(--text-sub);">${issue.name}</div>
            <div style="text-align: right;">
                <div style="font-weight: 600;">${issue.value}</div>
                <div style="font-size: 0.75rem; color: var(--success)">
                    ${issue.change}
                </div>
            </div>
        `;
        defiList.appendChild(div);
    });

    // 7. Update Strategic Verdict
    const verdict = document.getElementById('strategicVerdict');
    if (data.accumulation_gems && data.accumulation_gems.length > 0) {
        const bestGem = data.accumulation_gems[0];
        verdict.innerHTML = `
            현재 <strong>${bestGem.symbol}</strong> 종목이 역사적 <strong>${bestGem.analogy.case_name}</strong> 패턴과 
            <strong>${bestGem.analogy.similarity}%</strong> 유사한 매집 형태를 보이고 있습니다. 
            일론 머스크와 CZ의 소셜 시그니처가 결합될 경우 폭발적인 breakout이 예상됩니다. 
            이미 급등한 Trending 종목보다는 이 'Gems' 리스트에 주목하십시오.
        `;
    }
}

function getFGColor(value) {
    if (value < 25) return 'var(--danger)';
    if (value < 45) return 'var(--warning)';
    if (value < 60) return 'var(--text-main)';
    return 'var(--success)';
}

function getBadgeClass(status) {
    if (status === 'PUMPING') return 'badge-success';
    if (status === 'DUMPING') return 'badge-danger';
    return 'badge-warning';
}
