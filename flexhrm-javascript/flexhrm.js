// All elements are always available, just hidden?

function xpathAll(xpath) {
  let result = []
  try {
    xr = document.evaluate(xpath, document, null, XPathResult.UNORDERED_NODE_ITERATOR_TYPE, null);
  } catch (e) {
    console.log('Failed xpath:', xpath);
    throw(e);
  }
  while (node = xr.iterateNext()) {
    result.push(node);
  }
  return result;
}

function xpathOne(xpath) {
  return xpathAll(xpath)[0];
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitFor(func, ...args) {
  console.log(`  Wait for ${func.name}(${args.join(', ')})`);
  for (i = 0; i < 10; i++) {
    let result = func(...args);
    if (result) {
      console.log('    Found');
      return result;
    }
    console.log('    Waiting');
    await sleep(1000);
  }
  console.log('    Not found');
  throw new Error('Not found');
}

async function waitForElem(selector) {
  return waitFor(document.querySelector, selector);
}

async function waitVisible(selector) {
  return waitFor(isVisible, selector);
}

async function waitVisibleXpath(xpath) {
  return waitFor(isVisibleXpath, xpath);
}

function isVisible(selector) {
  return isVisibleElem(document.querySelector(selector));
}

function isVisibleXpath(xpath) {
  return isVisibleElem(xpathOne(xpath));
}

function isVisibleElem(el) {
  return el && (el.offsetParent !== null) && el
}

function triggerEvent(elem, eventName) {
  let event = new Event(eventName, { 'bubbles': true, 'cancelable': true });
  elem.dispatchEvent(event);
}

async function enterTime(field, hour, minute) {
  console.log(`enterTime(${field}, ${hour}, ${minute})`);
  (await waitVisible(`div[data-link=${field}]`)).click();
  
  var hourElem = document.querySelector('input[name=hour]');
  hourElem.value = hour;
  triggerEvent(hourElem, 'change');
  
  var minuteElem = document.querySelector('input[name=minute]');
  minuteElem.value = minute;
  triggerEvent(minuteElem, 'change');
  
  await sleep(1000);
  document.querySelector('#weekdayAndTimeOkButton').click()
}

async function setProject(query) {
  console.log(`setProject(${query})`);
  (await waitVisible('div[data-link=Kontering]')).click();
  await sleep(2000);
  accountField = document.querySelector('#konteringPage #flexListSearch');
  accountField.value = query;
  triggerEvent(accountField, 'keyup');
  await sleep(2000);
  document.querySelector('#KonteringScroll [data-type=kontering]').click();
  await sleep(1000);
}

async function setTimeCode(query) {
  console.log(`setTimeCode(${query})`);
  (await waitVisible('div[data-link=Tidkod]')).click();
  await sleep(2000);
  for (const elem of document.querySelectorAll('#flexList .flexListItem')) {
    if (elem.innerText.indexOf(query) != -1) {
      elem.click();
      break;
    }
  }
  await sleep(2000);
}

async function goToDate(dateString) {
  console.log(`goToDate(${dateString})`);

  targetDate = new Date(dateString);
  
  currentDate = new Date(document.querySelector('.middleContent p:nth-child(2)').innerText);
  safetyCounter = 0;
  while (currentDate.getTime() != targetDate.getTime() && safetyCounter++ < 20) {
    if (currentDate < targetDate) {
      document.querySelector('#tidrapportSammanstallningHeader .rightContent div').click()
    } else if (currentDate > targetDate) {
      document.querySelector('#tidrapportSammanstallningHeader .leftContent div').click()
    }
    let lastDate = currentDate;
    currentDate = new Date(document.querySelector('.middleContent p:nth-child(2)').innerText);
    while (currentDate.getTime() == lastDate.getTime()) {
      console.log('wait for date change');
      await sleep(1000);
      currentDate = new Date(document.querySelector('.middleContent p:nth-child(2)').innerText);
    }
  }
}

async function clearDay() {
  while (true) {
    let menuEntries = document.querySelectorAll('#tidrapportDagar .flexListItem[data-index]')
    if (menuEntries.length == 0) {
      break;
    }
    menuEntries[0].click();
    (await waitVisible('#deleteButton')).click();
    (await waitVisibleXpath('//a[contains(., "Ja")]')).click();
    await sleep(2000);
  }
}

async function reportDump(data) {
  if (data['system'] != 'flexhrm') {
    alert('Wrong system');
  } else if (data['days'].length != data['len']) {
    alert('Wrong length');
  } else {
    // Go to the time reporting page
    let startBtn = isVisible('#tidrapport.startButton');
    if (startBtn) {
      startBtn.click();
    }

    // Make sure we are on the right page
    waitVisibleXpath('//div[.="Tidrapport"]');

    for (const day of data['days']) {
      console.log('Day', day['date']);
      await goToDate(day['date']);
      for (entry of day['entries']) {
        console.log('Enter', entry);

        document.getElementById('newTidrad').click();
      
        let [timeCodeId, consultancyCompanyId, projectId] = entry['account'];
        
        await sleep(1000);

        await setTimeCode(timeCodeId);
        [hourStr, minStr, secStr] = entry['begin_time'].split(':')
        await enterTime('FromKlockslag', parseInt(hourStr), parseInt(minStr));

        [hourStr, minStr, secStr] = entry['end_time'].split(':')
        await enterTime('TomKlockslag', parseInt(hourStr), parseInt(minStr));

        if (projectId != null && projectId != '') {
          await setProject(projectId);
        }

        document.querySelector('#saveButton').click();
      }
    }
  }
}

async function report() {
  jsonData = prompt('Enter output from report.py flexhrm -j', '');
  if (jsonData) {
    let data = undefined;
    try {
      data = JSON.parse(jsonData);
    } catch (e) {
      alert(e);
    }
    if (data) {
      await reportDump(data);
      console.log('Done');
    }
  }
}

