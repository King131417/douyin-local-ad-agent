const { chromium } = require('playwright');
const path = require('path');
const os = require('os');

const ACCOUNT_ID = '1839326360573324';
const MARKETING_GOAL = '1';

const GENERAL_URL = `https://localads.chengzijianzhan.cn/lamp/pc/cdp_promotion/promote-manage/ad?advid=${ACCOUNT_ID}&marketingGoal=${MARKETING_GOAL}`;
const SEARCH_URL = `https://localads.chengzijianzhan.cn/lamp/pc/cdp_promotion/promote-manage/ad/search?advid=${ACCOUNT_ID}&marketingGoal=${MARKETING_GOAL}`;

async function scrapePage(browser, url, label) {
  console.log(`\n=== 正在打开 ${label} ===`);
  console.log(`URL: ${url}`);

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });
  const page = await context.newPage();

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    console.log('页面已加载');

    // Wait for data to render (the page likely loads data via AJAX)
    await page.waitForTimeout(5000);

    // Take a screenshot
    const screenshotPath = `/tmp/backend_${label}.png`;
    await page.screenshot({ path: screenshotPath, fullPage: false });
    console.log(`截图已保存: ${screenshotPath}`);

    // Try to extract the page title
    const title = await page.title();
    console.log(`标题: ${title}`);

    // Try to find any visible text that looks like numbers
    // Look for elements that might contain cost data
    const visibleText = await page.evaluate(() => {
      // Get all visible text content
      const body = document.body;
      if (!body) return 'NO BODY';

      // Try to find specific elements that contain financial data
      // Common patterns: spans, divs with specific classes
      const allText = body.innerText.substring(0, 3000);
      return allText;
    });
    console.log(`\n页面文本 (前3000字符):\n${visibleText}`);

    // Also try to get HTML with table/data elements
    const html = await page.evaluate(() => {
      // Look for elements that commonly contain data
      const selects = 'table, [class*="data"], [class*="table"], [class*="stat"], [class*="cost"], [class*="amount"]';
      const elements = document.querySelectorAll(selects);
      const results = [];
      elements.forEach(el => {
        const html = el.outerHTML.substring(0, 500);
        if (html.includes('¥') || html.includes('元') || /\d{4,}/.test(html)) {
          results.push(html);
        }
      });
      return results.slice(0, 20).join('\n---\n');
    });
    if (html) {
      console.log(`\n相关HTML元素:\n${html}`);
    }

    // Look for network requests that might be API calls
    const requests = [];
    page.on('request', req => {
      if (req.url().includes('api') || req.url().includes('report') || req.url().includes('data')) {
        requests.push(req.url());
      }
    });
    await page.waitForTimeout(3000);
    if (requests.length > 0) {
      console.log(`\n捕获的API请求: ${requests.join('\n')}`);
    }

    // Intercept network responses to find data
    const apiData = [];
    page.on('response', async resp => {
      const url = resp.url();
      if (url.includes('api') || url.includes('get') || url.includes('list') || url.includes('report')) {
        try {
          const body = await resp.text();
          if (body.length < 5000) {
            apiData.push({ url, body: body.substring(0, 2000) });
          }
        } catch (e) { }
      }
    });
    await page.waitForTimeout(3000);

    if (apiData.length > 0) {
      console.log(`\n捕获的API响应:`);
      apiData.forEach(d => {
        console.log(`  URL: ${d.url}`);
        console.log(`  Body (截断): ${d.body}`);
        console.log('  ---');
      });
    }

  } catch (e) {
    console.log(`错误: ${e.message}`);
  } finally {
    await context.close();
  }
}

(async () => {
  // Try using the user's Chrome profile
  const userDataDir = path.join(os.homedir(), 'Library', 'Application Support', 'Google', 'Chrome');

  console.log('正在启动浏览器...');
  console.log(`使用Chrome用户数据: ${userDataDir}`);

  let browser;
  try {
    // Try with user Chrome profile
    browser = await chromium.launchPersistentContext(userDataDir, {
      headless: true,
      channel: 'chrome',
      viewport: { width: 1920, height: 1080 },
    });
    console.log('已连接到Chrome用户数据');
  } catch (e) {
    console.log(`无法使用Chrome配置: ${e.message}`);
    console.log('使用默认无头浏览器...');
    browser = await chromium.launch({ headless: true });
  }

  try {
    await scrapePage(browser, GENERAL_URL, '通投');
    await scrapePage(browser, SEARCH_URL, '搜索');
  } finally {
    await browser.close();
    console.log('\n浏览器已关闭');
  }
})();
