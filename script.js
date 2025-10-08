const CSS_UNITS = 96.0 / 72.0;
const pdfjsLib = window['pdfjs-dist/build/pdf'];

if (pdfjsLib?.GlobalWorkerOptions) {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.2.67/pdf.worker.min.js';
}

const pdfInput = document.getElementById('pdfInput');
const canvas = document.getElementById('canvas');
const clearButton = document.getElementById('clearCanvas');
const exportButton = document.getElementById('exportHtml');
const inspector = {
  fontFamily: document.getElementById('fontFamily'),
  fontSize: document.getElementById('fontSize'),
  lineHeight: document.getElementById('lineHeight'),
  textColor: document.getElementById('textColor'),
  backgroundColor: document.getElementById('backgroundColor'),
  opacity: document.getElementById('opacity'),
  alignButtons: Array.from(document.querySelectorAll('[data-align]')),
  styleButtons: Array.from(document.querySelectorAll('[data-style]')),
  layerButtons: Array.from(document.querySelectorAll('[data-layer]')),
  rotation: document.getElementById('rotation'),
  scaleX: document.getElementById('scaleX'),
  scaleY: document.getElementById('scaleY'),
  duplicate: document.getElementById('duplicate'),
  delete: document.getElementById('delete'),
};

let currentPdf = null;
let selectedElement = null;

function createElementId() {
  if (window.crypto?.randomUUID) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

pdfInput?.addEventListener('change', async event => {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  const arrayBuffer = await file.arrayBuffer();
  const loadingTask = pdfjsLib.getDocument({
    data: arrayBuffer,
    useSystemFonts: true,
  });

  try {
    const pdf = await loadingTask.promise;
    currentPdf = pdf;
    renderPdf(pdf);
  } catch (error) {
    console.error('Failed to load PDF', error);
    alert('Unable to load the selected PDF file.');
  }
});

clearButton?.addEventListener('click', () => {
  currentPdf = null;
  canvas.innerHTML = `
    <div class="placeholder">
      <h2>Import a PDF to begin</h2>
      <p>The PDF will be rendered page-by-page with every element converted into an editable block.</p>
    </div>
  `;
});

exportButton?.addEventListener('click', () => {
  const cloned = document.documentElement.cloneNode(true);
  const scriptTags = cloned.querySelectorAll('script');
  scriptTags.forEach(tag => {
    if (!tag.src) {
      tag.remove();
    }
  });

  const blob = new Blob(['<!DOCTYPE html>\n', cloned.outerHTML], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'editable-pdf.html';
  link.click();
  URL.revokeObjectURL(url);
});

canvas.addEventListener('click', event => {
  const target = event.target.closest('.editable-block, .vector-block');
  if (target) {
    selectElement(target);
  } else {
    deselectElement();
  }
});

canvas.addEventListener('dblclick', event => {
  const target = event.target.closest('.editable-block');
  if (target) {
    target.focus();
    document.execCommand('selectAll', false, null);
  }
});

window.addEventListener('keydown', event => {
  if (!selectedElement) return;

  const { key } = event;
  const step = event.shiftKey ? 5 : 1;

  if ([
    'ArrowUp',
    'ArrowDown',
    'ArrowLeft',
    'ArrowRight',
  ].includes(key)) {
    event.preventDefault();
    const delta = {
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
    }[key];
    translateSelection(delta[0], delta[1]);
  }

  if (key === 'Delete' || key === 'Backspace') {
    deleteSelection();
  }
});

inspector.fontFamily?.addEventListener('change', () => {
  if (!selectedElement) return;
  selectedElement.style.fontFamily = inspector.fontFamily.value || selectedElement.dataset.originalFontFamily || '';
});

inspector.fontSize?.addEventListener('input', () => {
  if (!selectedElement) return;
  const size = parseFloat(inspector.fontSize.value);
  if (!Number.isFinite(size)) return;
  selectedElement.style.fontSize = `${size}px`;
});

inspector.lineHeight?.addEventListener('input', () => {
  if (!selectedElement) return;
  const value = parseFloat(inspector.lineHeight.value);
  if (!Number.isFinite(value)) return;
  selectedElement.style.lineHeight = `${value}`;
});

inspector.textColor?.addEventListener('change', () => {
  if (!selectedElement) return;
  selectedElement.style.color = inspector.textColor.value;
});

inspector.backgroundColor?.addEventListener('change', () => {
  if (!selectedElement) return;
  selectedElement.style.backgroundColor = inspector.backgroundColor.value;
});

inspector.opacity?.addEventListener('input', () => {
  if (!selectedElement) return;
  selectedElement.style.opacity = inspector.opacity.value;
});

inspector.alignButtons.forEach(button => {
  button.addEventListener('click', () => {
    if (!selectedElement) return;
    const align = button.dataset.align;
    selectedElement.style.textAlign = align;
    updateButtonGroup(inspector.alignButtons, button);
  });
});

inspector.styleButtons.forEach(button => {
  button.addEventListener('click', () => {
    if (!selectedElement) return;
    const styleType = button.dataset.style;

    if (styleType === 'bold') {
      selectedElement.style.fontWeight = toggleBinaryStyle(selectedElement.style.fontWeight, '700', selectedElement.dataset.originalFontWeight || '400');
    } else if (styleType === 'italic') {
      selectedElement.style.fontStyle = toggleBinaryStyle(selectedElement.style.fontStyle, 'italic', selectedElement.dataset.originalFontStyle || 'normal');
    } else if (styleType === 'underline') {
      selectedElement.style.textDecoration = toggleBinaryStyle(selectedElement.style.textDecoration, 'underline', 'none');
    }

    updateButtonGroup(inspector.styleButtons, button);
  });
});

inspector.layerButtons.forEach(button => {
  button.addEventListener('click', () => {
    if (!selectedElement) return;
    const direction = button.dataset.layer;
    adjustLayer(selectedElement, direction === 'forward' ? 1 : -1);
  });
});

inspector.rotation?.addEventListener('input', () => {
  if (!selectedElement) return;
  const rotation = parseFloat(inspector.rotation.value) || 0;
  selectedElement.dataset.rotation = rotation;
  applyCompositeTransform(selectedElement);
});

inspector.scaleX?.addEventListener('input', () => {
  if (!selectedElement) return;
  const scale = parseFloat(inspector.scaleX.value);
  if (!Number.isFinite(scale) || scale === 0) return;
  selectedElement.dataset.scaleX = scale;
  applyCompositeTransform(selectedElement);
});

inspector.scaleY?.addEventListener('input', () => {
  if (!selectedElement) return;
  const scale = parseFloat(inspector.scaleY.value);
  if (!Number.isFinite(scale) || scale === 0) return;
  selectedElement.dataset.scaleY = scale;
  applyCompositeTransform(selectedElement);
});

inspector.duplicate?.addEventListener('click', () => {
  if (!selectedElement) return;
  const clone = selectedElement.cloneNode(true);
  clone.dataset.elementId = createElementId();
  const cloneTranslateX = parseFloat(clone.dataset.translateX || '0');
  const cloneTranslateY = parseFloat(clone.dataset.translateY || '0');
  clone.dataset.translateX = (cloneTranslateX + 12).toString();
  clone.dataset.translateY = (cloneTranslateY + 12).toString();
  canvas.querySelector(`[data-page-index="${clone.dataset.pageIndex}"] .page`).appendChild(clone);
  initialiseEditableElement(clone);
  selectElement(clone);
});

inspector.delete?.addEventListener('click', () => {
  deleteSelection();
});

function translateSelection(dx, dy) {
  if (!selectedElement) return;
  const currentX = parseFloat(selectedElement.dataset.translateX || '0');
  const currentY = parseFloat(selectedElement.dataset.translateY || '0');
  selectedElement.dataset.translateX = currentX + dx;
  selectedElement.dataset.translateY = currentY + dy;
  applyCompositeTransform(selectedElement);
}

function adjustLayer(element, delta) {
  const current = parseInt(element.style.zIndex || element.dataset.zIndex || '1', 10);
  const next = Math.max(1, current + delta);
  element.style.zIndex = String(next);
  element.dataset.zIndex = String(next);
}

function toggleBinaryStyle(current, activeValue, defaultValue) {
  return current === activeValue ? defaultValue : activeValue;
}

function updateButtonGroup(buttons, activeButton) {
  buttons.forEach(button => {
    if (button === activeButton) {
      button.classList.toggle('active');
    } else {
      button.classList.remove('active');
    }
  });
}

async function renderPdf(pdf) {
  canvas.innerHTML = '';
  const pageCount = pdf.numPages;

  for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
    const page = await pdf.getPage(pageNumber);
    const viewport = page.getViewport({ scale: CSS_UNITS });
    const pageWrapper = document.createElement('div');
    pageWrapper.className = 'page-wrapper';
    pageWrapper.dataset.pageIndex = pageNumber - 1;

    const pageElement = document.createElement('div');
    pageElement.className = 'page';
    pageElement.dataset.pageIndex = pageNumber - 1;
    pageElement.style.width = `${viewport.width}px`;
    pageElement.style.height = `${viewport.height}px`;

    const backgroundElement = document.createElement('div');
    backgroundElement.className = 'page-background';
    backgroundElement.style.width = '100%';
    backgroundElement.style.height = '100%';
    pageElement.appendChild(backgroundElement);

    const pixelRatio = window.devicePixelRatio || 1;
    const canvasElement = document.createElement('canvas');
    canvasElement.width = Math.floor(viewport.width * pixelRatio);
    canvasElement.height = Math.floor(viewport.height * pixelRatio);
    const ctx = canvasElement.getContext('2d');
    const renderViewport = page.getViewport({ scale: CSS_UNITS * pixelRatio });
    ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    await page.render({ canvasContext: ctx, viewport: renderViewport }).promise;
    backgroundElement.style.backgroundImage = `url(${canvasElement.toDataURL('image/png')})`;

    await renderSvgVectorLayer(page, viewport, pageElement);
    await renderTextLayer(page, viewport, pageElement, pageNumber - 1);

    pageWrapper.appendChild(pageElement);
    canvas.appendChild(pageWrapper);
  }
}

async function renderSvgVectorLayer(page, viewport, pageElement) {
  try {
    const opList = await page.getOperatorList();
    const svgGfx = new pdfjsLib.SVGGraphics(page.commonObjs, page.objs);
    svgGfx.embedFonts = true;
    const svg = await svgGfx.getSVG(opList, viewport);
    svg.setAttribute('width', `${viewport.width}`);
    svg.setAttribute('height', `${viewport.height}`);
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    svg.style.opacity = '0';
    svg.style.pointerEvents = 'none';
    svg.classList.add('page-svg-layer');
    pageElement.appendChild(svg);
    convertSvgToVectorBlocks(svg, pageElement);
  } catch (error) {
    console.warn('SVG vector layer is not available', error);
  }
}

function convertSvgToVectorBlocks(svg, pageElement) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const defs = svg.querySelector('defs');
  const defsString = defs ? new XMLSerializer().serializeToString(defs) : '';
  const nodes = Array.from(svg.children).filter(node => node.tagName !== 'defs');

  nodes.forEach((node, index) => {
    if (typeof node.getBBox !== 'function') {
      return;
    }

    let bbox;
    try {
      bbox = node.getBBox();
    } catch (error) {
      return;
    }

    if (!bbox || bbox.width === 0 || bbox.height === 0) {
      return;
    }

    const block = document.createElement('div');
    block.className = 'vector-block';
    block.dataset.elementId = createElementId();
    block.dataset.pageIndex = pageElement.dataset.pageIndex || '0';
    block.dataset.baseXAxis = '1,0';
    block.dataset.baseYAxis = '0,1';
    block.dataset.baseTranslate = `${bbox.x},${bbox.y}`;
    block.dataset.translateX = '0';
    block.dataset.translateY = '0';
    block.dataset.scaleX = '1';
    block.dataset.scaleY = '1';
    block.dataset.rotation = '0';
    block.tabIndex = 0;

    block.style.width = `${bbox.width}px`;
    block.style.height = `${bbox.height}px`;
    block.style.transformOrigin = '0 0';

    const blockSvg = document.createElementNS(svgNS, 'svg');
    blockSvg.setAttribute('xmlns', svgNS);
    blockSvg.setAttribute('viewBox', `0 0 ${bbox.width} ${bbox.height}`);
    blockSvg.setAttribute('width', `${bbox.width}`);
    blockSvg.setAttribute('height', `${bbox.height}`);
    blockSvg.style.width = '100%';
    blockSvg.style.height = '100%';
    blockSvg.style.pointerEvents = 'none';

    if (defsString) {
      blockSvg.insertAdjacentHTML('afterbegin', defsString);
    }

    const wrapper = document.createElementNS(svgNS, 'g');
    wrapper.setAttribute('transform', `translate(${-bbox.x},${-bbox.y})`);
    wrapper.appendChild(node.cloneNode(true));
    blockSvg.appendChild(wrapper);

    block.appendChild(blockSvg);
    const zIndex = pageElement.children.length + 1;
    block.dataset.zIndex = String(zIndex);
    block.style.zIndex = block.dataset.zIndex;
    pageElement.appendChild(block);
    initialiseEditableElement(block);
  });

  svg.remove();
}

async function renderTextLayer(page, viewport, pageElement, pageIndex) {
  const textContent = await page.getTextContent({ includeMarkedContent: true, disableCombineTextItems: false });
  const styles = textContent.styles || {};

  textContent.items.forEach((item, index) => {
    const transform = pdfjsLib.Util.transform(viewport.transform, item.transform);
    const element = document.createElement('div');
    element.className = 'editable-block';
    element.setAttribute('contenteditable', 'true');
    element.dataset.elementId = createElementId();
    element.dataset.pageIndex = pageIndex;
    element.dataset.translateX = '0';
    element.dataset.translateY = '0';
    element.dataset.rotation = '0';
    element.dataset.scaleX = '1';
    element.dataset.scaleY = '1';
    element.dataset.baseTransform = transform.join(',');

    const baseXAxis = [transform[0], transform[1]];
    const baseYAxis = [transform[2], transform[3]];
    const baseTranslate = [transform[4], transform[5]];

    element.dataset.baseXAxis = baseXAxis.join(',');
    element.dataset.baseYAxis = baseYAxis.join(',');
    element.dataset.baseTranslate = baseTranslate.join(',');

    const font = styles[item.fontName] || {};
    element.dataset.originalFontFamily = font.fontFamily || '';
    element.dataset.originalFontWeight = font.fontWeight || '400';
    element.dataset.originalFontStyle = font.fontStyle || 'normal';

    const fontHeight = Math.hypot(transform[2], transform[3]);
    const width = item.width * viewport.scale;

    element.style.transform = `matrix(${transform.join(',')})`;
    element.style.transformOrigin = '0 0';
    element.style.height = `${fontHeight}px`;
    element.style.width = `${width}px`;
    element.style.fontSize = `${fontHeight}px`;
    element.style.lineHeight = `${item.height ? item.height * viewport.scale : fontHeight}px`;
    element.style.fontFamily = font.fontFamily || 'inherit';
    element.style.fontWeight = font.fontWeight || '400';
    element.style.fontStyle = font.fontStyle || 'normal';
    element.style.color = item.rgb ? `rgb(${item.rgb[0] * 255}, ${item.rgb[1] * 255}, ${item.rgb[2] * 255})` : '#000000';

    element.textContent = item.str;

    initialiseEditableElement(element);
    const zIndex = pageElement.children.length + 1;
    element.dataset.zIndex = String(zIndex);
    element.style.zIndex = element.dataset.zIndex;
    pageElement.appendChild(element);
  });
}

function initialiseEditableElement(element) {
  element.addEventListener('focus', () => selectElement(element));
  element.addEventListener('input', () => {
    element.dataset.contentLength = element.textContent.length;
  });

  if (!element.hasAttribute('tabindex')) {
    element.tabIndex = 0;
  }

  if (!element.dataset.translateX) {
    element.dataset.translateX = '0';
    element.dataset.translateY = '0';
    element.dataset.rotation = '0';
    element.dataset.scaleX = '1';
    element.dataset.scaleY = '1';
  }

  applyCompositeTransform(element);

  interact(element).draggable({
    listeners: {
      move(event) {
        const dx = event.dx;
        const dy = event.dy;
        const currentX = parseFloat(element.dataset.translateX || '0');
        const currentY = parseFloat(element.dataset.translateY || '0');
        element.dataset.translateX = currentX + dx;
        element.dataset.translateY = currentY + dy;
        applyCompositeTransform(element);
      },
    },
  }).styleCursor(false);

  interact(element).resizable({
    edges: { left: false, right: true, bottom: true, top: false },
    listeners: {
      move(event) {
        const scaleX = parseFloat(element.dataset.scaleX || '1');
        const scaleY = parseFloat(element.dataset.scaleY || '1');
        const width = Math.max(1, parseFloat(element.style.width || '0'));
        const height = Math.max(1, parseFloat(element.style.height || '0'));
        const newScaleX = (width + event.deltaRect.width) / width;
        const newScaleY = (height + event.deltaRect.height) / height;
        element.dataset.scaleX = scaleX * newScaleX;
        element.dataset.scaleY = scaleY * newScaleY;
        inspector.scaleX.value = parseFloat(element.dataset.scaleX).toFixed(2);
        inspector.scaleY.value = parseFloat(element.dataset.scaleY).toFixed(2);
        applyCompositeTransform(element);
      },
    },
    modifiers: [
      interact.modifiers.restrictEdges({
        outer: 'parent',
      }),
    ],
  });
}

function selectElement(element) {
  if (selectedElement === element) return;
  deselectElement();
  selectedElement = element;
  selectedElement.dataset.selected = 'true';
  selectedElement.focus({ preventScroll: true });
  refreshInspector(element);
}

function deselectElement() {
  if (!selectedElement) return;
  selectedElement.dataset.selected = 'false';
  selectedElement = null;
  inspector.alignButtons.forEach(btn => btn.classList.remove('active'));
  inspector.styleButtons.forEach(btn => btn.classList.remove('active'));
}

function refreshInspector(element) {
  const computed = window.getComputedStyle(element);
  inspector.fontFamily.value = '';
  inspector.fontSize.value = parseFloat(computed.fontSize) || '';
  inspector.lineHeight.value = parseFloat(computed.lineHeight) || '';
  inspector.textColor.value = rgbStringToHex(computed.color);
  inspector.backgroundColor.value = rgbStringToHex(computed.backgroundColor);
  inspector.opacity.value = parseFloat(computed.opacity) || 1;
  inspector.rotation.value = parseFloat(element.dataset.rotation || '0');
  inspector.scaleX.value = parseFloat(element.dataset.scaleX || '1').toFixed(2);
  inspector.scaleY.value = parseFloat(element.dataset.scaleY || '1').toFixed(2);

  inspector.alignButtons.forEach(button => {
    const align = button.dataset.align;
    if (computed.textAlign === align) {
      button.classList.add('active');
    } else {
      button.classList.remove('active');
    }
  });

  inspector.styleButtons.forEach(button => {
    const styleType = button.dataset.style;
    let isActive = false;
    if (styleType === 'bold') {
      isActive = computed.fontWeight === '700' || parseInt(computed.fontWeight, 10) >= 600;
    } else if (styleType === 'italic') {
      isActive = computed.fontStyle === 'italic';
    } else if (styleType === 'underline') {
      isActive = computed.textDecorationLine.includes('underline');
    }
    button.classList.toggle('active', isActive);
  });
}

function rgbStringToHex(rgbString) {
  if (!rgbString || rgbString === 'transparent') {
    return '#000000';
  }
  const rgbMatch = /rgb\((\d+),\s*(\d+),\s*(\d+)\)/i.exec(rgbString);
  const rgbaMatch = /rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)/i.exec(rgbString);
  const match = rgbMatch || rgbaMatch;
  if (!match) {
    return '#000000';
  }
  return `#${match.slice(1, 4).map(value => Number(value).toString(16).padStart(2, '0')).join('')}`;
}

function applyCompositeTransform(element) {
  const baseXAxis = element.dataset.baseXAxis?.split(',').map(Number) || [1, 0];
  const baseYAxis = element.dataset.baseYAxis?.split(',').map(Number) || [0, 1];
  const baseTranslate = element.dataset.baseTranslate?.split(',').map(Number) || [0, 0];

  const rotation = parseFloat(element.dataset.rotation || '0');
  const rotationRad = (rotation * Math.PI) / 180;
  const scaleX = parseFloat(element.dataset.scaleX || '1');
  const scaleY = parseFloat(element.dataset.scaleY || '1');
  const translateX = parseFloat(element.dataset.translateX || '0');
  const translateY = parseFloat(element.dataset.translateY || '0');

  const cos = Math.cos(rotationRad);
  const sin = Math.sin(rotationRad);

  const rotatedXAxis = {
    x: baseXAxis[0] * cos - baseXAxis[1] * sin,
    y: baseXAxis[0] * sin + baseXAxis[1] * cos,
  };

  const rotatedYAxis = {
    x: baseYAxis[0] * cos - baseYAxis[1] * sin,
    y: baseYAxis[0] * sin + baseYAxis[1] * cos,
  };

  const xAxis = {
    x: rotatedXAxis.x * scaleX,
    y: rotatedXAxis.y * scaleX,
  };

  const yAxis = {
    x: rotatedYAxis.x * scaleY,
    y: rotatedYAxis.y * scaleY,
  };

  const tx = baseTranslate[0] + translateX;
  const ty = baseTranslate[1] + translateY;

  const matrix = [xAxis.x, xAxis.y, yAxis.x, yAxis.y, tx, ty];
  element.style.transform = `matrix(${matrix.join(',')})`;
  element.dataset.computedMatrix = matrix.join(',');
}

function deleteSelection() {
  if (!selectedElement) return;
  const element = selectedElement;
  deselectElement();
  element.remove();
}

// Initialise InteractJS defaults for cursor hints
if (window.interact) {
  interact('.page').dropzone({ accept: '.editable-block, .vector-block' });
}
