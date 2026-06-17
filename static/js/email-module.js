
// Features: GSAP Animations, TipTap Integration, AI Agent Interactions

// ========================================
// GSAP Animations
// ========================================
function initGSAPAnimations() {
  if (typeof gsap === 'undefined') return;

  // Page entrance animations
  if (document.querySelector('.page-shell')) {
    gsap.from('.page-shell', {
      opacity: 0,
      y: 20,
      duration: 0.5,
      ease: 'power2.out',
    });
  }

  // Card stagger animations
  if (document.querySelector('.glass-card')) {
    gsap.from('.glass-card', {
      opacity: 0,
      y: 15,
      duration: 0.4,
      stagger: 0.08,
      ease: 'power2.out',
      scrollTrigger: { trigger: '.glass-card', start: 'top 90%' }
    });
  }

  // Button hover effects
  document.querySelectorAll('.btn-animated').forEach(btn => {
    btn.addEventListener('mouseenter', () => {
      gsap.to(btn, { scale: 1.02, duration: 0.2, ease: 'power2.out' });
    });
    btn.addEventListener('mouseleave', () => {
      gsap.to(btn, { scale: 1, duration: 0.2, ease: 'power2.out' });
    });
  });

  // Step progress animation
  document.querySelectorAll('.step-circle').forEach((el, i) => {
    gsap.from(el, {
      scale: 0,
      duration: 0.3,
      delay: i * 0.1,
      ease: 'back.out(1.7)',
    });
  });

  // Toast notifications
  document.querySelectorAll('.toast-item').forEach(toast => {
    gsap.from(toast, {
      x: 50,
      opacity: 0,
      duration: 0.4,
      ease: 'power2.out',
    });
    setTimeout(() => {
      gsap.to(toast, {
        x: 50,
        opacity: 0,
        duration: 0.4,
        delay: 3,
        ease: 'power2.in',
        onComplete: () => toast.remove(),
      });
    }, 100);
  });
}

// Initialize animations on page load
document.addEventListener('DOMContentLoaded', initGSAPAnimations);

// Reinitialize after HTMX/AJAX loads
document.addEventListener('htmx:afterSwap', initGSAPAnimations);

// ========================================
// TipTap Rich Text Editor
// ========================================
var tiptapEditor = null;

function initTipTap(elementId, options) {
  if (typeof Tiptap === 'undefined') return;

  var element = document.getElementById(elementId);
  if (!element) return;

  var editor = new Tiptap.Editor({
    element: element,
    extensions: [
      Tiptap.StarterKit.configure({
        bulletList: { keepMarks: true, keepAttributes: false },
        orderedList: { keepMarks: true, keepAttributes: false },
      }),
      Tiptap.Placeholder.configure({
        placeholder: 'Write your email content here...',
      }),
      Tiptap.Link.configure({
        openOnClick: false,
        HTMLAttributes: { rel: 'noopener noreferrer', target: '_blank' },
      }),
      Tiptap.Image.configure({ inline: true, allowBase64: true }),
      Tiptap.TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Tiptap.Underline,
      Tiptap.History.configure({ depth: 100 }),
    ],
    editorProps: {
      attributes: {
        class: 'prose prose-sm max-w-none focus:outline-none min-h-[200px] p-4',
      },
    },
    onUpdate: function() {
      var html = editor.getHTML();
      var text = editor.getText();
      var hiddenInput = document.getElementById(elementId + '_hidden');
      if (hiddenInput) {
        hiddenInput.value = html;
      }
      var counter = document.getElementById(elementId + '_counter');
      if (counter) {
        counter.textContent = text.length + ' characters';
      }
      // Dispatch custom event
      document.dispatchEvent(new CustomEvent('tiptap:update', {
        detail: { id: elementId, html: html, text: text }
      }));
    },
  });

  // Set initial content
  if (options && options.content) {
    editor.commands.setContent(options.content);
  }

  tiptapEditor = editor;
  return editor;
}

function destroyTipTap() {
  if (tiptapEditor) {
    tiptapEditor.destroy();
    tiptapEditor = null;
  }
}

// ========================================
// AI Agent Interactions
// ========================================
var AIClient = {
  apiKey: null,
  baseUrl: window.location.origin,

  init: function() {
    // Get CSRF token
    this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
    if (this.csrfToken) {
      this.csrfToken = this.csrfToken.value;
    }
  },

  generateDraft: function(messageId, tone, callback) {
    var btn = document.getElementById('ai-generate-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<svg class="animate-spin -ml-1 mr-2 h-4 w-4 inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Generating...';
    }

    fetch('/inbox/generate-draft/' + messageId + '/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': this.csrfToken,
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Tone': tone || 'professional',
      },
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        if (callback) callback(data.draft_body);
        // Show success toast
        showToast('success', 'AI draft generated successfully!');
      } else {
        showToast('error', data.error || 'Failed to generate draft');
      }
    })
    .catch(function(err) {
      showToast('error', 'Network error: ' + err.message);
    })
    .finally(function() {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg> Generate with AI';
      }
    });
  },

  summarizeMessage: function(messageId) {
    var btn = document.getElementById('summarize-btn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = 'Summarizing...';
    }
    fetch('/inbox/summarize/' + messageId + '/', {
      method: 'POST',
      headers: { 'X-CSRFToken': this.csrfToken },
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        showToast('success', 'Message summarized');
        location.reload();
      } else {
        showToast('error', data.error || 'Failed to summarize');
      }
    })
    .catch(function(err) {
      showToast('error', 'Error: ' + err.message);
    })
    .finally(function() {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Summarize'; }
    });
  },
};

// ========================================
// Toast Notification System
// ========================================
function showToast(type, message) {
  var container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed top-4 right-4 z-[9999] flex flex-col gap-2';
    document.body.appendChild(container);
  }

  var icons = {
    success: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    warning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.25c-.77.833.192 2.5 1.732 2.5z"/>',
    info: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
  };

  var bgColors = {
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    error: 'bg-red-50 border-red-200 text-red-800',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
    info: 'bg-blue-50 border-blue-200 text-blue-800',
  };

  var toast = document.createElement('div');
  toast.className = 'toast-item flex items-start gap-3 p-4 rounded-xl border shadow-lg backdrop-blur-sm ' + (bgColors[type] || 'bg-white border-slate-200 text-slate-800');
  toast.innerHTML =
    '<svg class="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">' +
    (icons[type] || icons.info) + '</svg>' +
    '<span class="text-sm font-medium flex-1">' + message + '</span>' +
    '<button onclick="this.parentElement.remove()" class="shrink-0 text-current opacity-50 hover:opacity-100">' +
    '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg></button>';

  container.appendChild(toast);

  // Animate in with GSAP
  if (typeof gsap !== 'undefined') {
    gsap.from(toast, { x: 50, opacity: 0, duration: 0.3, ease: 'power2.out' });
    setTimeout(function() {
      gsap.to(toast, { x: 100, opacity: 0, duration: 0.3, delay: 4, ease: 'power2.in', onComplete: function() { toast.remove(); }});
    }, 100);
  } else {
    setTimeout(function() { toast.remove(); }, 5000);
  }
}

// ========================================
// Campaign Wizard
// ========================================
var CampaignWizard = {
  currentStep: 0,
  steps: [],

  init: function() {
    var steps = document.querySelectorAll('.step-panel');
    if (!steps.length) return;
    // Page already has its own goToStep (campaign create/edit) — skip
    if (typeof goToStep === 'function') return;

    this.steps = steps;
    this.currentStep = 0;
    this.showStep(0);
  },

  showStep: function(index) {
    var self = this;
    this.steps.forEach(function(step, i) {
      if (i === index) {
        step.style.display = 'block';
        if (typeof gsap !== 'undefined') {
          gsap.from(step, { opacity: 0, x: 20, duration: 0.3, ease: 'power2.out' });
        }
      } else {
        step.style.display = 'none';
      }
    });

    // Update progress
    document.querySelectorAll('.step-btn').forEach(function(btn, i) {
      btn.classList.toggle('active', i === index);
      btn.classList.toggle('completed', i < index);
    });

    // Update buttons
    var prevBtn = document.getElementById('wizard-prev');
    var nextBtn = document.getElementById('wizard-next');
    var submitBtn = document.getElementById('wizard-submit');

    if (prevBtn) prevBtn.style.display = index === 0 ? 'none' : 'inline-flex';
    if (submitBtn) {
      submitBtn.style.display = index === this.steps.length - 1 ? 'inline-flex' : 'none';
    }
    if (nextBtn) {
      if (index < this.steps.length - 1 && !submitBtn) {
        nextBtn.style.display = 'inline-flex';
      } else {
        nextBtn.style.display = 'none';
      }
    }

    this.currentStep = index;
  },

  nextStep: function() {
    if (this.currentStep < this.steps.length - 1) {
      this.showStep(this.currentStep + 1);
    }
  },

  prevStep: function() {
    if (this.currentStep > 0) {
      this.showStep(this.currentStep - 1);
    }
  }
};

// ========================================
// Inbox Dashboard
// ========================================
var InboxDashboard = {
  init: function() {
    this.bindSearch();
    this.bindFolderTabs();
    this.initAIAssist();
  },

  bindSearch: function() {
    var searchInput = document.getElementById('inbox-search');
    if (!searchInput) return;

    var debounceTimer;
    searchInput.addEventListener('input', function() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function() {
        var query = searchInput.value.trim();
        var url = new URL(window.location.href);
        if (query) {
          url.searchParams.set('q', query);
        } else {
          url.searchParams.delete('q');
        }
        window.location.href = url.toString();
      }, 400);
    });
  },

  bindFolderTabs: function() {
    document.querySelectorAll('.folder-tab').forEach(function(tab) {
      tab.addEventListener('click', function(e) {
        var folder = this.dataset.folder;
        if (folder) {
          var url = new URL(window.location.href);
          url.searchParams.set('folder', folder);
          url.searchParams.delete('page');
          window.location.href = url.toString();
        }
      });
    });
  },

  initAIAssist: function() {
    AIClient.init();
  },

  bulkAction: function(action) {
    var selected = document.querySelectorAll('.message-checkbox:checked');
    if (!selected.length) {
      showToast('warning', 'Select at least one message.');
      return;
    }

    var ids = Array.from(selected).map(function(cb) { return cb.value; });
    fetch('/inbox/bulk-action/', {
      method: 'POST',
      headers: {
        'X-CSRFToken': AIClient.csrfToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ action: action, message_ids: ids }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        showToast('success', action === 'delete' ? 'Messages moved to trash' : 'Messages processed');
        location.reload();
      } else {
        showToast('error', data.error || 'Action failed');
      }
    })
    .catch(function(err) {
      showToast('error', err.message);
    });
  }
};

// ========================================
// Send Confirmation Modal (Email Module)
// ========================================
var EmailSendModal = {
  currentForm: null,
  
  open: function(formElement) {
    this.currentForm = formElement;
    var modal = document.getElementById('send-confirmation-modal');
    if (modal) {
      modal.style.display = 'flex';
      document.body.classList.add('overflow-hidden');
    }
  },
  
  close: function() {
    var modal = document.getElementById('send-confirmation-modal');
    if (modal) {
      modal.style.display = 'none';
      document.body.classList.remove('overflow-hidden');
    }
    this.currentForm = null;
  },
  
  confirm: function() {
    if (this.currentForm) {
      this.close();
      this.currentForm.submit();
    }
  }
};

// Global functions for modal
window.openSendModal = function(formElement) {
  EmailSendModal.open(formElement);
};

window.closeSendModal = function() {
  EmailSendModal.close();
};

window.confirmAndSend = function() {
  EmailSendModal.confirm();
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  InboxDashboard.init();
  CampaignWizard.init();
  window.showToast = showToast;
  window.AIClient = AIClient;
  window.EmailSendModal = EmailSendModal;
});


