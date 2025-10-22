const state = {
  document: null,
  selectedElementId: null,
  dirty: false,
};

const pagesContainer = document.getElementById('pages');
const statusEl = document.getElementById('status');
const fileInput = document.getElementById('fileInput');
const saveButton = document.getElementById('saveButton');
const downloadButton = document.getElementById('downloadButton');
const summaryButton = document.getElementById('summaryButton');
const inspectorContent = document.getElementById('inspectorContent');
const inspectorTemplate = document.getElementById('inspectorTemplate');
const bringForwardButton = document.getElementById('bringForward');
const sendBackwardButton = document.getElementById('sendBackward');

let inspectorForm = null;

fileInput.addEventListener('change', handleFileUpload);
saveButton.addEventListener('click', saveLayout);
downloadButton.addEventListener('click', downloadPdf);
summaryButton.addEventListener('click', showSummary);
bringForwardButton.addEventListener('click', () => reorderSelected(1));
sendBackwardButton.addEventListener('click', () => reorderSelected(-1));

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? '#ffe0e0' : '#fefefe';
}

function setButtonsEnabled(enabled) {
  saveButton.disabled = !enabled;
  downloadButton.disabled = !enabled;
  summaryButton.disabled = !enabled;
}

function markDirty() {
  state.dirty = true;
  saveButton.disabled = false;
  setStatus('Unsaved changes');
}

function clearDirty() {
  state.dirty = false;
  setStatus('Changes saved');
}

function handleFileUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  setStatus(`Uploading ${file.name}...`);
  fetch('/api/upload', {
    method: 'POST',
    body: formData,
  })
    .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        throw new Error(data.error || 'Upload failed');
      }
      state.document = data.document;
      renderDocument(state.document);
      setButtonsEnabled(true);
      clearDirty();
      setStatus(`Loaded ${file.name}`);
    })
    .catch((error) => {
      console.error(error);
      setStatus(error.message, true);
    });
}

function renderDocument(doc) {
  pagesContainer.innerHTML = '';
  state.selectedElementId = null;
  inspectorContent.innerHTML = '<p>Select an element to edit its properties.</p>';
  inspectorForm = null;

  if (!doc || !doc.pages || doc.pages.length === 0) {
    setStatus('Document has no pages');
    return;
  }

  doc.pages.forEach((page) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'page-wrapper';
    wrapper.style.width = `${page.width}px`;
    wrapper.style.height = `${page.height}px`;
    wrapper.dataset.index = page.index;

    page.elements
      .slice()
      .sort((a, b) => a.order - b.order)
      .forEach((element) => {
        const node = renderElement(element, page);
        wrapper.appendChild(node);
      });

    pagesContainer.appendChild(wrapper);
  });
}

function renderElement(element, page) {
  const node = document.createElement('div');
  node.className = `element element-${element.type}`;
  node.dataset.id = element.id;
  node.dataset.type = element.type;
  node.dataset.pageIndex = page.index;
  node.dataset.order = element.order;
  node.dataset.x = element.x;
  node.dataset.y = element.y;
  node.dataset.width = element.width;
  node.dataset.height = element.height;
  node.style.left = `${element.x}px`;
  node.style.top = `${element.y}px`;
  node.style.zIndex = element.order;
  node.style.width = `${element.width}px`;
  node.style.height = `${element.height}px`;

  if (element.type === 'text') {
    node.dataset.fontSize = element.fontSize;
    const editor = document.createElement('div');
    editor.className = 'text-editor';
    editor.contentEditable = 'true';
    editor.style.fontSize = `${element.fontSize}px`;
    editor.textContent = element.text;
    editor.addEventListener('input', () => {
      updateTextMetrics(node);
      markDirty();
      if (state.selectedElementId === node.dataset.id && inspectorForm) {
        inspectorForm.elements.text.value = editor.textContent;
      }
    });
    node.appendChild(editor);
    updateTextMetrics(node);
  } else if (element.type === 'image') {
    const img = document.createElement('img');
    img.src = element.src;
    img.alt = `Image ${element.name}`;
    node.appendChild(img);
  }

  node.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    node.setPointerCapture(event.pointerId);
    node.dataset.dragStartX = event.clientX;
    node.dataset.dragStartY = event.clientY;
    node.dataset.originalX = node.dataset.x;
    node.dataset.originalY = node.dataset.y;
    event.preventDefault();
  });

  node.addEventListener('pointermove', (event) => {
    if (!node.hasPointerCapture(event.pointerId)) return;
    const wrapper = node.parentElement;
    if (!wrapper) return;
    const rect = wrapper.getBoundingClientRect();
    const width = parseFloat(node.dataset.width) || 0;
    const height = parseFloat(node.dataset.height) || 0;
    const startX = parseFloat(node.dataset.dragStartX);
    const startY = parseFloat(node.dataset.dragStartY);
    const originalX = parseFloat(node.dataset.originalX);
    const originalY = parseFloat(node.dataset.originalY);
    const deltaX = event.clientX - startX;
    const deltaY = event.clientY - startY;
    let nextX = originalX + deltaX;
    let nextY = originalY + deltaY;
    nextX = Math.min(Math.max(0, nextX), rect.width - width);
    nextY = Math.min(Math.max(0, nextY), rect.height - height);
    node.style.left = `${nextX}px`;
    node.style.top = `${nextY}px`;
    node.dataset.x = nextX.toFixed(2);
    node.dataset.y = nextY.toFixed(2);
    markDirty();
    if (state.selectedElementId === node.dataset.id && inspectorForm) {
      inspectorForm.elements.x.value = nextX.toFixed(2);
      inspectorForm.elements.y.value = nextY.toFixed(2);
    }
  });

  node.addEventListener('pointerup', (event) => {
    if (node.hasPointerCapture(event.pointerId)) {
      node.releasePointerCapture(event.pointerId);
    }
  });

  node.addEventListener('pointercancel', (event) => {
    if (node.hasPointerCapture(event.pointerId)) {
      node.releasePointerCapture(event.pointerId);
    }
  });

  node.addEventListener('click', (event) => {
    event.stopPropagation();
    selectElement(node);
  });

  return node;
}

pagesContainer.addEventListener('click', () => {
  deselectElement();
});

function selectElement(node) {
  if (!node) return;
  if (state.selectedElementId === node.dataset.id) return;
  deselectElement();
  node.classList.add('selected');
  state.selectedElementId = node.dataset.id;
  updateInspector(node);
  bringForwardButton.disabled = false;
  sendBackwardButton.disabled = false;
}

function deselectElement() {
  const previous = document.querySelector('.element.selected');
  if (previous) {
    previous.classList.remove('selected');
  }
  state.selectedElementId = null;
  inspectorContent.innerHTML = '<p>Select an element to edit its properties.</p>';
  inspectorForm = null;
  bringForwardButton.disabled = true;
  sendBackwardButton.disabled = true;
}

function updateInspector(node) {
  inspectorContent.innerHTML = '';
  const fragment = inspectorTemplate.content.cloneNode(true);
  inspectorForm = fragment.getElementById('inspectorForm');
  inspectorForm.elements.type.value = node.dataset.type;
  inspectorForm.elements.x.value = parseFloat(node.dataset.x).toFixed(2);
  inspectorForm.elements.y.value = parseFloat(node.dataset.y).toFixed(2);
  inspectorForm.elements.width.value = parseFloat(node.dataset.width).toFixed(2);
  inspectorForm.elements.height.value = parseFloat(node.dataset.height).toFixed(2);
  inspectorForm.elements.text.disabled = node.dataset.type !== 'text';
  inspectorForm.elements.fontSize.disabled = node.dataset.type !== 'text';

  if (node.dataset.type === 'text') {
    inspectorForm.elements.text.value = node.querySelector('.text-editor').textContent;
    inspectorForm.elements.fontSize.value = parseFloat(node.dataset.fontSize).toFixed(2);
  } else {
    inspectorForm.elements.text.value = '';
    inspectorForm.elements.fontSize.value = '';
  }

  inspectorForm.addEventListener('input', () => handleInspectorInput(node));
  inspectorForm.addEventListener('change', () => handleInspectorInput(node));
  inspectorContent.appendChild(fragment);
}

function handleInspectorInput(node) {
  if (!inspectorForm) return;
  const x = parseFloat(inspectorForm.elements.x.value);
  const y = parseFloat(inspectorForm.elements.y.value);
  const width = parseFloat(inspectorForm.elements.width.value);
  const height = parseFloat(inspectorForm.elements.height.value);

  if (!Number.isNaN(x)) {
    node.style.left = `${x}px`;
    node.dataset.x = x.toFixed(2);
  }
  if (!Number.isNaN(y)) {
    node.style.top = `${y}px`;
    node.dataset.y = y.toFixed(2);
  }
  if (!Number.isNaN(width)) {
    node.style.width = `${width}px`;
    node.dataset.width = width.toFixed(2);
  }
  if (!Number.isNaN(height)) {
    node.style.height = `${height}px`;
    node.dataset.height = height.toFixed(2);
  }

  if (node.dataset.type === 'text') {
    const editor = node.querySelector('.text-editor');
    const textValue = inspectorForm.elements.text.value;
    const fontSize = parseFloat(inspectorForm.elements.fontSize.value);
    if (textValue !== undefined) {
      editor.textContent = textValue;
      updateTextMetrics(node);
    }
    if (!Number.isNaN(fontSize)) {
      editor.style.fontSize = `${fontSize}px`;
      node.dataset.fontSize = fontSize.toFixed(2);
      node.dataset.height = fontSize.toFixed(2);
      node.style.height = `${fontSize}px`;
    }
  }

  markDirty();
}

function updateTextMetrics(node) {
  const editor = node.querySelector('.text-editor');
  if (!editor) return;
  const range = document.createRange();
  range.selectNodeContents(editor);
  const rects = range.getBoundingClientRect();
  const width = Math.max(rects.width, 32);
  const height = Math.max(rects.height, parseFloat(node.dataset.fontSize) || 16);
  node.style.width = `${width}px`;
  node.style.height = `${height}px`;
  node.dataset.width = width.toFixed(2);
  node.dataset.height = height.toFixed(2);
  if (inspectorForm) {
    inspectorForm.elements.width.value = width.toFixed(2);
    inspectorForm.elements.height.value = height.toFixed(2);
  }
}

function reorderSelected(direction) {
  const node = getSelectedNode();
  if (!node) return;
  const wrapper = node.parentElement;
  if (!wrapper) return;
  const elements = Array.from(wrapper.querySelectorAll('.element')).sort(
    (a, b) => Number(a.dataset.order) - Number(b.dataset.order),
  );
  const index = elements.indexOf(node);
  const nextIndex = Math.min(Math.max(index + direction, 0), elements.length - 1);
  if (index === nextIndex) return;
  elements.splice(index, 1);
  elements.splice(nextIndex, 0, node);
  elements.forEach((element, idx) => {
    element.dataset.order = idx;
    element.style.zIndex = idx;
    wrapper.appendChild(element);
  });
  markDirty();
}

function getSelectedNode() {
  if (!state.selectedElementId) return null;
  return document.querySelector(`.element[data-id="${state.selectedElementId}"]`);
}

function collectPayload() {
  const pages = [];
  document.querySelectorAll('.page-wrapper').forEach((wrapper) => {
    const elements = Array.from(wrapper.querySelectorAll('.element')).map((node) => {
      const payload = {
        id: node.dataset.id,
        type: node.dataset.type,
        order: Number(node.dataset.order),
        x: parseFloat(node.dataset.x),
        y: parseFloat(node.dataset.y),
        width: parseFloat(node.dataset.width),
        height: parseFloat(node.dataset.height),
      };
      if (node.dataset.type === 'text') {
        payload.text = node.querySelector('.text-editor').textContent;
        payload.fontSize = parseFloat(node.dataset.fontSize);
      }
      return payload;
    });
    pages.push({ page_index: Number(wrapper.dataset.index), elements });
  });
  return { pages };
}

function saveLayout() {
  const payload = collectPayload();
  setStatus('Saving changes...');
  fetch('/api/document', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
    .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        throw new Error(data.error || 'Failed to save');
      }
      state.document = data.document;
      clearDirty();
    })
    .catch((error) => {
      console.error(error);
      setStatus(error.message, true);
    });
}

function downloadPdf() {
  setStatus('Preparing PDF for download...');
  fetch('/api/document/pdf')
    .then((response) => {
      if (!response.ok) {
        return response.json().then((data) => {
          throw new Error(data.error || 'Download failed');
        });
      }
      return response.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'edited.pdf';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setStatus('Downloaded edited PDF');
    })
    .catch((error) => {
      console.error(error);
      setStatus(error.message, true);
    });
}

function showSummary() {
  fetch('/api/document/summary')
    .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        throw new Error(data.error || 'Unable to build summary');
      }
      inspectorContent.innerHTML = '';
      const list = document.createElement('ul');
      list.className = 'summary-list';
      data.pages.forEach((page) => {
        const item = document.createElement('li');
        item.textContent = `Page ${page.index + 1}: ${page.textElements} text, ${page.imageElements} images`;
        list.appendChild(item);
      });
      inspectorContent.appendChild(list);
      setStatus('Summary generated');
    })
    .catch((error) => {
      console.error(error);
      setStatus(error.message, true);
    });
}

function initialLoad() {
  fetch('/api/document')
    .then((response) => response.json())
    .then((doc) => {
      if (doc.pages && doc.pages.length) {
        state.document = doc;
        renderDocument(doc);
        setButtonsEnabled(true);
        setStatus('Loaded last document');
      }
    })
    .catch(() => {
      setStatus('Ready to load a PDF');
    });
}

initialLoad();
