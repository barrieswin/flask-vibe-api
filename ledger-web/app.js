/**
 * 個人記帳本前端主程式
 * 嚴格遵循 docs/前端串接.md 規範：
 * 1. 頂層回應結構 code / message / data，失敗時只顯示人話 message，連不上顯示「目前連不上記帳服務」。
 * 2. GET 請求不附帶 Content-Type（維持 CORS 簡單請求），帶有 _t 當下毫秒時間戳與 cache: 'no-store'。
 * 3. 網址 localhost:5000 自動正規化為 127.0.0.1:5000（避免 macOS AirPlay 403）。
 * 4. 客戶端不送 id、created_at、updated_at。
 */

(() => {
  const STORAGE_KEY = 'ledger.connection';

  // 內部狀態
  const state = {
    apiBaseUrl: '',
    currentTab: 'home',
    recordMode: 'expense', // 'expense' | 'income'
    accounts: [],
    incomeCategories: [],
    expenseCategories: [],
    monthlyRecords: [],
  };

  // 工具函式：取得當前月份字串 YYYY-MM
  function getCurrentMonthKey() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    return `${y}-${m}`;
  }

  // 工具函式：取得當前今天日期 YYYY-MM-DD
  function getTodayDateString() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  // 工具函式：格式化金額為千分位帶兩位或整數
  function formatAmount(val) {
    const num = Number(val);
    if (isNaN(num)) return '0.00';
    return num.toLocaleString('zh-TW', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  // 工具函式：過濾客戶端不送的欄位 (id, created_at, updated_at)
  function sanitizePayload(payload) {
    if (!payload || typeof payload !== 'object') return payload;
    const clean = { ...payload };
    delete clean.id;
    delete clean.created_at;
    delete clean.updated_at;
    return clean;
  }

  // 訊息提示控制（全域與連線頁）
  function showMessage(elementId, text, type = 'error') {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = text;
    el.className = `message-banner ${type}`;
    el.style.display = 'block';

    if (elementId === 'global-msg' && type === 'success') {
      setTimeout(() => {
        el.style.display = 'none';
      }, 3500);
    }
  }

  function hideMessage(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
      el.style.display = 'none';
      el.textContent = '';
    }
  }

  // 1. URL 正規化：若主機是 localhost 且連接埠是 5000，改為 127.0.0.1
  function normalizeApiUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') {
      throw new Error('請輸入後端 API 網址');
    }
    const trimmed = rawUrl.trim();
    if (!/^https?:\/\//i.test(trimmed)) {
      throw new Error('網址必須以 http:// 或 https:// 開頭');
    }

    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        throw new Error('網址必須以 http:// 或 https:// 開頭');
      }
      if (parsed.hostname === 'localhost' && parsed.port === '5000') {
        parsed.hostname = '127.0.0.1';
      }
      // 去除結尾多餘斜線
      const normalized = (parsed.origin + parsed.pathname).replace(/\/+$/, '');
      return normalized;
    } catch (err) {
      if (err.message.includes('http')) throw err;
      throw new Error('網址格式不正確');
    }
  }

  // 2. 封裝 API 請求
  async function apiRequest(path, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    let url = `${state.apiBaseUrl}${path}`;

    const fetchOptions = {
      method,
      cache: 'no-store',
      mode: 'cors',
      headers: {},
    };

    // GET 請求：加上 _t 毫秒時間戳，且絕不加 Content-Type 以維持 CORS 簡單請求
    if (method === 'GET') {
      const separator = url.includes('?') ? '&' : '?';
      url = `${url}${separator}_t=${Date.now()}`;
    } else {
      // POST, PATCH 等有正文的請求：加上 Content-Type
      fetchOptions.headers['Content-Type'] = 'application/json';
      if (options.body) {
        const cleanBody = sanitizePayload(options.body);
        fetchOptions.body = JSON.stringify(cleanBody);
      }
    }

    try {
      const response = await fetch(url, fetchOptions);
      const json = await response.json();
      return json;
    } catch (err) {
      // 網路斷線、CORS 阻擋或無法解析 JSON
      return {
        code: 0,
        message: '目前連不上記帳服務',
        data: null,
      };
    }
  }

  // 3. 連線處理
  async function handleConnect() {
    hideMessage('connect-msg');
    const input = document.getElementById('input-api-url');
    const btn = document.getElementById('btn-connect');

    let normalizedUrl;
    try {
      normalizedUrl = normalizeApiUrl(input.value);
    } catch (err) {
      showMessage('connect-msg', err.message, 'error');
      return;
    }

    btn.disabled = true;
    btn.textContent = '連線測試中...';

    // 暫存 base url 測試 /api/health
    state.apiBaseUrl = normalizedUrl;
    const res = await apiRequest('/api/health');

    btn.disabled = false;
    btn.textContent = '連線並測試';

    if (res.code === 200 && res.data && res.data.status === 'ok') {
      // 寫入 localStorage 的 ledger.connection，只存 apiBaseUrl
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiBaseUrl: normalizedUrl }));
      enterMainApp();
    } else {
      const errMsg = res.message || '目前連不上記帳服務';
      showMessage('connect-msg', errMsg, 'error');
    }
  }

  // 清除連線
  function clearConnection() {
    localStorage.removeItem(STORAGE_KEY);
    state.apiBaseUrl = '';
    document.getElementById('view-main').classList.add('hidden');
    document.getElementById('view-connect').classList.remove('hidden');
    hideMessage('global-msg');
    hideMessage('connect-msg');
  }

  // 進入主畫面
  function enterMainApp() {
    document.getElementById('view-connect').classList.add('hidden');
    document.getElementById('view-main').classList.remove('hidden');
    switchTab('home');
  }

  // 分頁切換
  function switchTab(tabName) {
    state.currentTab = tabName;
    hideMessage('global-msg');

    // 更新底部導覽按鈕高亮
    const navButtons = document.querySelectorAll('.nav-item');
    navButtons.forEach((btn) => btn.classList.remove('active'));
    const activeNav = document.getElementById(`nav-btn-${tabName}`);
    if (activeNav) activeNav.classList.add('active');

    // 切換分頁顯示
    const panes = document.querySelectorAll('.tab-pane');
    panes.forEach((pane) => pane.classList.add('hidden'));
    const targetPane = document.getElementById(`tab-${tabName}`);
    if (targetPane) targetPane.classList.remove('hidden');

    // 載入該分頁資料
    if (tabName === 'home') {
      loadHomeData();
    } else if (tabName === 'records') {
      loadRecordsData();
    } else if (tabName === 'investment') {
      loadInvestmentData();
    } else if (tabName === 'invoices') {
      loadInvoicesData();
    }
  }

  // ==========================================
  // 分頁 1：首頁邏輯（Summary + Accounts & Balances）
  // ==========================================
  async function loadHomeData() {
    const monthKey = getCurrentMonthKey();
    const monthLabelEl = document.getElementById('home-month-label');
    if (monthLabelEl) monthLabelEl.textContent = `${monthKey} 月份`;

    // 1. 取得本月收支摘要
    const summaryRes = await apiRequest(`/api/summary?month=${monthKey}`);
    if (summaryRes.code === 200 && summaryRes.data) {
      const income = Number(summaryRes.data.income_twd || 0);
      const expense = Number(summaryRes.data.expense_twd || 0);
      const net = income - expense;

      document.getElementById('home-income-val').textContent = `$ ${formatAmount(income)}`;
      document.getElementById('home-expense-val').textContent = `$ ${formatAmount(expense)}`;

      const netEl = document.getElementById('home-net-val');
      netEl.textContent = `$ ${formatAmount(net)}`;
      netEl.className = `amount ${net >= 0 ? 'income' : 'expense'}`;
    } else {
      showMessage('global-msg', summaryRes.message || '目前連不上記帳服務', 'error');
    }

    // 2. 取得帳戶清單與個別餘額
    const accRes = await apiRequest('/api/accounts');
    const accContainer = document.getElementById('home-accounts-container');
    const createBox = document.getElementById('home-create-account-box');

    if (accRes.code === 200 && Array.isArray(accRes.data)) {
      state.accounts = accRes.data;

      if (state.accounts.length === 0) {
        accContainer.innerHTML = '<div class="empty-state">尚未建立任何資金帳戶</div>';
        createBox.classList.remove('hidden');
      } else {
        createBox.classList.add('hidden');
        accContainer.innerHTML = '<div class="account-list" id="home-account-list"></div>';
        const listEl = document.getElementById('home-account-list');

        // 平行查各帳戶的餘額
        const balancePromises = state.accounts.map(async (acc) => {
          const balRes = await apiRequest(`/api/accounts/${acc.id}/balance`);
          const twdBalance = (balRes.code === 200 && balRes.data) ? balRes.data.twd_balance : 0;
          return { acc, twdBalance };
        });

        const balances = await Promise.all(balancePromises);
        listEl.innerHTML = '';
        balances.forEach(({ acc, twdBalance }) => {
          const item = document.createElement('div');
          item.className = 'account-item';
          const kindMap = {
            cash: '現金',
            bank: '銀行',
            credit_card: '信用卡',
            broker: '證券交割',
          };
          item.innerHTML = `
            <div class="account-meta">
              <span class="account-name">${acc.name}</span>
              <span class="account-kind">${kindMap[acc.kind] || acc.kind}（${acc.currency}）</span>
            </div>
            <div class="amount neutral" style="font-size: 1.05rem;">
              $ ${formatAmount(twdBalance)}
            </div>
          `;
          listEl.appendChild(item);
        });
      }
    } else {
      accContainer.innerHTML = '<div class="empty-state">無法載入帳戶資料</div>';
      showMessage('global-msg', accRes.message || '目前連不上記帳服務', 'error');
    }
  }

  // 首頁：快速建立預設現金帳戶
  async function createDefaultAccount() {
    const btn = document.getElementById('btn-create-default-account');
    btn.disabled = true;
    btn.textContent = '建立中...';

    const payload = {
      name: '現金錢包',
      kind: 'cash',
      currency: 'TWD',
      opening_balance: 0.0,
      statement_day: null,
      payment_day: null,
    };

    const res = await apiRequest('/api/accounts', {
      method: 'POST',
      body: payload,
    });

    btn.disabled = false;
    btn.textContent = '建立現金錢包';

    if (res.code === 201) {
      showMessage('global-msg', '現金帳戶建立成功！', 'success');
      loadHomeData();
    } else {
      showMessage('global-msg', res.message || '建立帳戶失敗', 'error');
    }
  }

  // ==========================================
  // 分頁 2：記帳邏輯（Expense / Income Forms & List）
  // ==========================================
  function switchRecordMode(mode) {
    state.recordMode = mode;
    const btnExpense = document.getElementById('btn-mode-expense');
    const btnIncome = document.getElementById('btn-mode-income');
    const formExpense = document.getElementById('form-expense');
    const formIncome = document.getElementById('form-income');
    const quickBox = document.getElementById('quick-category-box');

    quickBox.classList.add('hidden');

    if (mode === 'expense') {
      btnExpense.classList.add('active');
      btnIncome.classList.remove('active');
      formExpense.classList.remove('hidden');
      formIncome.classList.add('hidden');
    } else {
      btnExpense.classList.remove('active');
      btnIncome.classList.add('active');
      formExpense.classList.add('hidden');
      formIncome.classList.remove('hidden');
    }
    populateDropdowns();
  }

  // 載入記帳所需之分類、帳戶與當月流水
  async function loadRecordsData() {
    // 預設日期為今天
    const today = getTodayDateString();
    document.getElementById('expense-spent-on').value = today;
    document.getElementById('income-received-on').value = today;

    // 平行拉取分類與帳戶
    const [incCatRes, expCatRes, accRes] = await Promise.all([
      apiRequest('/api/income-categories'),
      apiRequest('/api/expense-categories'),
      apiRequest('/api/accounts'),
    ]);

    if (incCatRes.code === 200) state.incomeCategories = incCatRes.data || [];
    if (expCatRes.code === 200) state.expenseCategories = expCatRes.data || [];
    if (accRes.code === 200) state.accounts = accRes.data || [];

    populateDropdowns();

    // 載入當月流水記錄
    loadMonthlyRecords();
  }

  // 填充分類與帳戶下拉選單
  function populateDropdowns() {
    const expCatSelect = document.getElementById('expense-category-id');
    const incCatSelect = document.getElementById('income-category-id');
    const expAccSelect = document.getElementById('expense-account-id');
    const incAccSelect = document.getElementById('income-account-id');

    // 帳戶選單
    const accOptionsHtml = state.accounts.length === 0
      ? '<option value="">(尚未建立帳戶)</option>'
      : state.accounts.map((a) => `<option value="${a.id}">${a.name} (${a.currency})</option>`).join('');

    expAccSelect.innerHTML = accOptionsHtml;
    incAccSelect.innerHTML = accOptionsHtml;

    // 花費分類選單
    if (state.expenseCategories.length === 0) {
      expCatSelect.innerHTML = '<option value="">(無分類，請先新增分類)</option>';
    } else {
      expCatSelect.innerHTML = state.expenseCategories
        .map((c) => `<option value="${c.id}">${c.name}</option>`)
        .join('');
    }

    // 入帳分類選單
    if (state.incomeCategories.length === 0) {
      incCatSelect.innerHTML = '<option value="">(無分類，請先新增分類)</option>';
    } else {
      incCatSelect.innerHTML = state.incomeCategories
        .map((c) => `<option value="${c.id}">${c.name}</option>`)
        .join('');
    }
  }

  // 快速新增分類面板開關
  function toggleQuickCategory(mode) {
    const box = document.getElementById('quick-category-box');
    const title = document.getElementById('quick-category-title');
    const input = document.getElementById('input-quick-category-name');
    input.value = '';

    if (!box.classList.contains('hidden')) {
      box.classList.add('hidden');
      return;
    }

    title.textContent = mode === 'expense' ? '快速新增花費分類' : '快速新增入帳分類';
    box.dataset.mode = mode;
    box.classList.remove('hidden');
    input.focus();
  }

  // 提交快速新增分類
  async function submitQuickCategory() {
    const box = document.getElementById('quick-category-box');
    const input = document.getElementById('input-quick-category-name');
    const mode = box.dataset.mode || state.recordMode;
    const name = input.value.trim();

    if (!name) {
      showMessage('global-msg', '請輸入分類名稱', 'error');
      return;
    }

    const endpoint = mode === 'expense' ? '/api/expense-categories' : '/api/income-categories';
    const res = await apiRequest(endpoint, {
      method: 'POST',
      body: { name },
    });

    if (res.code === 201 && res.data) {
      showMessage('global-msg', '分類新增成功！', 'success');
      box.classList.add('hidden');

      if (mode === 'expense') {
        state.expenseCategories.push(res.data);
        populateDropdowns();
        document.getElementById('expense-category-id').value = res.data.id;
      } else {
        state.incomeCategories.push(res.data);
        populateDropdowns();
        document.getElementById('income-category-id').value = res.data.id;
      }
    } else {
      showMessage('global-msg', res.message || '新增分類失敗', 'error');
    }
  }

  // 送出花費記錄
  async function submitExpense() {
    hideMessage('global-msg');
    const spentOn = document.getElementById('expense-spent-on').value;
    const amountVal = document.getElementById('expense-amount').value;
    const categoryIdVal = document.getElementById('expense-category-id').value;
    const accountIdVal = document.getElementById('expense-account-id').value;
    const merchant = document.getElementById('expense-merchant').value.trim();
    const note = document.getElementById('expense-note').value.trim();

    if (!amountVal || Number(amountVal) <= 0) {
      showMessage('global-msg', '花費金額必須大於 0', 'error');
      return;
    }
    if (!categoryIdVal) {
      showMessage('global-msg', '請先選擇或新增花費分類', 'error');
      return;
    }
    if (!accountIdVal) {
      showMessage('global-msg', '請先建立或選擇扣款帳戶', 'error');
      return;
    }
    if (!merchant && !note) {
      showMessage('global-msg', '商戶與備註不可同時為空，至少需填寫一項', 'error');
      return;
    }

    const payload = {
      spent_on: spentOn,
      amount: Number(amountVal),
      category_id: parseInt(categoryIdVal, 10),
      account_id: parseInt(accountIdVal, 10),
      merchant: merchant || null,
      note: note || null,
    };

    const res = await apiRequest('/api/expenses', {
      method: 'POST',
      body: payload,
    });

    if (res.code === 201 && res.data) {
      showMessage('global-msg', '花費記錄新增成功！', 'success');
      // 清空金額、商戶與備註
      document.getElementById('expense-amount').value = '';
      document.getElementById('expense-merchant').value = '';
      document.getElementById('expense-note').value = '';

      // 成功後將新列放在本月清單最上方
      prependRecordItem({
        type: 'expense',
        date: res.data.spent_on,
        title: res.data.merchant || res.data.note || '花費',
        note: res.data.note || '',
        amount: res.data.amount,
        currency: res.data.currency,
      });
    } else {
      showMessage('global-msg', res.message || '新增花費失敗', 'error');
    }
  }

  // 送出入帳記錄
  async function submitIncome() {
    hideMessage('global-msg');
    const receivedOn = document.getElementById('income-received-on').value;
    const amountVal = document.getElementById('income-amount').value;
    const categoryIdVal = document.getElementById('income-category-id').value;
    const accountIdVal = document.getElementById('income-account-id').value;
    const source = document.getElementById('income-source').value.trim();
    const note = document.getElementById('income-note').value.trim();

    if (!amountVal || Number(amountVal) <= 0) {
      showMessage('global-msg', '入帳金額必須大於 0', 'error');
      return;
    }
    if (!categoryIdVal) {
      showMessage('global-msg', '請先選擇或新增入帳分類', 'error');
      return;
    }
    if (!accountIdVal) {
      showMessage('global-msg', '請先建立或選擇收款帳戶', 'error');
      return;
    }
    if (!source && !note) {
      showMessage('global-msg', '來源與備註不可同時為空，至少需填寫一項', 'error');
      return;
    }

    const payload = {
      received_on: receivedOn,
      amount: Number(amountVal),
      category_id: parseInt(categoryIdVal, 10),
      account_id: parseInt(accountIdVal, 10),
      source: source || null,
      note: note || null,
    };

    const res = await apiRequest('/api/incomes', {
      method: 'POST',
      body: payload,
    });

    if (res.code === 201 && res.data) {
      showMessage('global-msg', '入帳記錄新增成功！', 'success');
      // 清空金額、來源與備註
      document.getElementById('income-amount').value = '';
      document.getElementById('income-source').value = '';
      document.getElementById('income-note').value = '';

      // 成功後將新列放在本月清單最上方
      prependRecordItem({
        type: 'income',
        date: res.data.received_on,
        title: res.data.source || res.data.note || '入帳',
        note: res.data.note || '',
        amount: res.data.amount,
        currency: res.data.currency,
      });
    } else {
      showMessage('global-msg', res.message || '新增入帳失敗', 'error');
    }
  }

  // 載入本月流水記錄清單
  async function loadMonthlyRecords() {
    const monthKey = getCurrentMonthKey();
    const dateFrom = `${monthKey}-01`;
    const dateTo = `${monthKey}-31`;

    const [incRes, expRes] = await Promise.all([
      apiRequest(`/api/incomes?date_from=${dateFrom}&date_to=${dateTo}`),
      apiRequest(`/api/expenses?date_from=${dateFrom}&date_to=${dateTo}`),
    ]);

    const records = [];
    if (incRes.code === 200 && Array.isArray(incRes.data)) {
      incRes.data.forEach((r) => {
        records.push({
          type: 'income',
          date: r.received_on,
          title: r.source || r.note || '入帳',
          note: r.note || '',
          amount: r.amount,
          currency: r.currency,
          rawDate: new Date(r.received_on).getTime(),
        });
      });
    }

    if (expRes.code === 200 && Array.isArray(expRes.data)) {
      expRes.data.forEach((r) => {
        records.push({
          type: 'expense',
          date: r.spent_on,
          title: r.merchant || r.note || '花費',
          note: r.note || '',
          amount: r.amount,
          currency: r.currency,
          rawDate: new Date(r.spent_on).getTime(),
        });
      });
    }

    // 依日期新到舊排序
    records.sort((a, b) => b.rawDate - a.rawDate);
    state.monthlyRecords = records;
    renderRecordsList();
  }

  function renderRecordsList() {
    const container = document.getElementById('monthly-records-container');
    if (!container) return;

    if (state.monthlyRecords.length === 0) {
      container.innerHTML = '<div class="empty-state">本月尚無明細記錄</div>';
      return;
    }

    container.innerHTML = '';
    state.monthlyRecords.forEach((item) => {
      container.appendChild(createRecordElement(item));
    });
  }

  // 建立流水項目 DOM 節點
  function createRecordElement(item) {
    const el = document.createElement('div');
    el.className = 'record-item';
    const isIncome = item.type === 'income';
    el.innerHTML = `
      <div class="record-meta">
        <span class="record-title">${item.title}</span>
        <span class="record-sub">${item.date}${item.note && item.note !== item.title ? ` · ${item.note}` : ''}</span>
      </div>
      <div class="amount ${isIncome ? 'income' : 'expense'}">
        ${isIncome ? '+' : '-'} $ ${formatAmount(item.amount)}
      </div>
    `;
    return el;
  }

  // 成功記帳後把新列插入在最上方
  function prependRecordItem(item) {
    state.monthlyRecords.unshift(item);
    const container = document.getElementById('monthly-records-container');
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const el = createRecordElement(item);
    container.insertBefore(el, container.firstChild);
  }

  // ==========================================
  // 分頁 3：投資邏輯（台股持有狀況與報價）
  // ==========================================
  async function loadInvestmentData() {
    const container = document.getElementById('investment-list-container');
    container.innerHTML = '<div class="empty-state">載入台股標的中...</div>';

    const instRes = await apiRequest('/api/instruments');
    if (instRes.code === 200 && Array.isArray(instRes.data)) {
      // 篩選 market 為 tw_stock 的標的
      const twStocks = instRes.data.filter((item) => item.market === 'tw_stock');

      if (twStocks.length === 0) {
        container.innerHTML = '<div class="empty-state">目前尚未建立台股投資標的</div>';
        return;
      }

      container.innerHTML = '';

      // 對每一檔標的，查詢 holding 與 quote
      const stockCardsPromises = twStocks.map(async (stock) => {
        const [holdingRes, quoteRes] = await Promise.all([
          apiRequest(`/api/instruments/${stock.id}/holding`),
          apiRequest(`/api/instruments/${stock.id}/quote`),
        ]);

        let quantity = 0;
        let avgCost = 0;
        let quoteText = '還沒有報價';

        if (holdingRes.code === 200 && holdingRes.data) {
          quantity = Number(holdingRes.data.quantity || 0);
          avgCost = Number(holdingRes.data.average_cost || 0);
        }

        if (quoteRes.code === 200 && quoteRes.data && quoteRes.data.price != null) {
          quoteText = `$ ${formatAmount(quoteRes.data.price)}`;
        }

        return {
          stock,
          quantity,
          avgCost,
          quoteText,
        };
      });

      const cardsData = await Promise.all(stockCardsPromises);
      cardsData.forEach(({ stock, quantity, avgCost, quoteText }) => {
        const item = document.createElement('div');
        item.className = 'stock-item';
        item.innerHTML = `
          <div class="stock-meta">
            <span class="stock-name">${stock.name} <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: normal;">(${stock.symbol})</span></span>
            <span class="stock-sub">持有股數：${quantity.toLocaleString('zh-TW')} 股 · 均價：$ ${formatAmount(avgCost)}</span>
          </div>
          <div style="text-align: right;">
            <div class="amount neutral" style="font-size: 1rem;">${quoteText}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">最新報價</div>
          </div>
        `;
        container.appendChild(item);
      });
    } else {
      container.innerHTML = '<div class="empty-state">無法載入投資標的</div>';
      showMessage('global-msg', instRes.message || '目前連不上記帳服務', 'error');
    }
  }

  // 抓取台股報價
  async function fetchStockQuotes() {
    const btn = document.getElementById('btn-fetch-quotes');
    const statusEl = document.getElementById('investment-quote-status');
    btn.disabled = true;
    btn.textContent = '報價抓取中...';
    statusEl.style.display = 'none';

    const res = await apiRequest('/api/tw-stock-quotes/fetch', {
      method: 'POST',
      body: {},
    });

    btn.disabled = false;
    btn.textContent = '🔄 抓取最新報價';

    if (res.code === 200) {
      let sentence = res.message || '台股報價更新完成';
      if (res.data && typeof res.data === 'object') {
        const skipped = Array.isArray(res.data.skipped) ? res.data.skipped.length : 0;
        const missing = Array.isArray(res.data.missing) ? res.data.missing.length : 0;
        if (skipped > 0 || missing > 0) {
          sentence = `報價更新完成（略過 ${skipped} 筆，查無 ${missing} 筆）`;
        }
      }
      statusEl.textContent = sentence;
      statusEl.className = 'message-banner info';
      statusEl.style.display = 'block';
    } else {
      statusEl.textContent = res.message || '目前連不上記帳服務';
      statusEl.className = 'message-banner error';
      statusEl.style.display = 'block';
    }

    // 重新整理投資清單
    await loadInvestmentData();
  }

  // ==========================================
  // 分頁 4：統一發票邏輯（唯讀清單）
  // ==========================================
  async function loadInvoicesData() {
    const container = document.getElementById('invoices-list-container');
    container.innerHTML = '<div class="empty-state">載入發票中...</div>';

    const res = await apiRequest('/api/invoices');
    if (res.code === 200 && Array.isArray(res.data)) {
      if (res.data.length === 0) {
        container.innerHTML = '<div class="empty-state">目前尚無統一發票記錄</div>';
        return;
      }

      container.innerHTML = '';
      const statusMap = {
        unchecked: { text: '未對獎', cls: 'badge-pending' },
        lost: { text: '未中獎', cls: 'badge-lost' },
        won: { text: '已中獎', cls: 'badge-won' },
        claimed: { text: '已兌獎', cls: 'badge-claimed' },
        void: { text: '已作廢', cls: 'badge-void' },
      };

      res.data.forEach((inv) => {
        const item = document.createElement('div');
        item.className = 'invoice-item';
        const st = statusMap[inv.prize_status] || { text: inv.prize_status, cls: 'badge-pending' };
        item.innerHTML = `
          <div class="invoice-meta">
            <span class="invoice-number">${inv.number} <span class="badge ${st.cls}">${st.text}</span></span>
            <span class="invoice-sub">${inv.issued_on} · ${inv.seller_name || '無店家名稱'}</span>
          </div>
          <div class="amount neutral" style="font-size: 1rem;">
            $ ${formatAmount(inv.amount)}
          </div>
        `;
        container.appendChild(item);
      });
    } else {
      container.innerHTML = '<div class="empty-state">無法載入發票資料</div>';
      showMessage('global-msg', res.message || '目前連不上記帳服務', 'error');
    }
  }

  // ==========================================
  // 初始化與生命週期
  // ==========================================
  async function initApp() {
    // 綁定按鈕事件
    document.getElementById('btn-clear-conn').addEventListener('click', clearConnection);
    document.getElementById('btn-create-default-account').addEventListener('click', createDefaultAccount);
    document.getElementById('btn-submit-quick-category').addEventListener('click', submitQuickCategory);

    // 檢查 localStorage 是否有儲存的連線設定
    const rawStored = localStorage.getItem(STORAGE_KEY);
    if (rawStored) {
      try {
        const stored = JSON.parse(rawStored);
        if (stored && stored.apiBaseUrl) {
          state.apiBaseUrl = normalizeApiUrl(stored.apiBaseUrl);
          document.getElementById('input-api-url').value = state.apiBaseUrl;

          // 重新檢查健康檢查
          const res = await apiRequest('/api/health');
          if (res.code === 200 && res.data && res.data.status === 'ok') {
            enterMainApp();
            return;
          } else {
            // 連線失敗，停在連線頁並顯示錯誤人話
            document.getElementById('view-connect').classList.remove('hidden');
            showMessage('connect-msg', res.message || '目前連不上記帳服務', 'error');
            return;
          }
        }
      } catch (err) {
        localStorage.removeItem(STORAGE_KEY);
      }
    }

    // 尚未連線過或解析失敗，預設停在連線頁
    document.getElementById('view-connect').classList.remove('hidden');
  }

  // 暴露公開操作給 HTML inline onclick 或全域
  window.app = {
    handleConnect,
    clearConnection,
    switchTab,
    switchRecordMode,
    toggleQuickCategory,
    submitQuickCategory,
    submitExpense,
    submitIncome,
    fetchStockQuotes,
  };

  // 當 DOM 載入完成時啟動
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
  } else {
    initApp();
  }
})();
