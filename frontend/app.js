// 自动适配当前域名（特别是为了 Ngrok 支持），因此保持为空字符串使用相对路径
const API_URL = "";

let currentUserToken = localStorage.getItem('user_token');
let currentUsername = localStorage.getItem('user_name');

window.onload = function() {
    checkLoginStatus();
};

function checkLoginStatus() {
    if (!currentUserToken) {
        document.getElementById('loginModal').classList.remove('hidden');
        document.getElementById('userInfo').style.display = 'none';
        document.getElementById('chatbox').innerHTML = ''; // clear chatbox
    } else {
        document.getElementById('loginModal').classList.add('hidden');
        document.getElementById('userInfo').style.display = 'block';
        document.getElementById('currentUsername').innerText = currentUsername;
        loadHistory();
    }
}

async function handleLogin() {
    const user = document.getElementById('usernameInput').value.trim();
    const pass = document.getElementById('passwordInput').value.trim();
    const errorEl = document.getElementById('loginError');
    if (!user || !pass) { errorEl.innerText = "Username and password cannot be empty"; return; }
    
    try {
        const res = await fetch(`${API_URL}/api/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user, password: pass})
        });
        const data = await res.json();
        if (res.ok) {
            currentUserToken = data.token;
            currentUsername = data.username;
            localStorage.setItem('user_token', data.token);
            localStorage.setItem('user_name', data.username);
            checkLoginStatus();
        } else {
            errorEl.innerText = data.detail || "Login failed";
        }
    } catch (e) {
        errorEl.innerText = "Network error: " + e;
    }
}

async function handleRegister() {
    const user = document.getElementById('usernameInput').value.trim();
    const pass = document.getElementById('passwordInput').value.trim();
    const errorEl = document.getElementById('loginError');
    if (!user || !pass) { errorEl.innerText = "Username and password cannot be empty"; return; }

    try {
        const res = await fetch(`${API_URL}/api/register`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user, password: pass})
        });
        const data = await res.json();
        if (res.ok) {
            errorEl.style.color = "green";
            errorEl.innerText = "Registration successful! Please login";
            setTimeout(() => { errorEl.style.color = "#dc3545"; errorEl.innerText = ""; }, 3000);
        } else {
            errorEl.innerText = data.detail || "Registration failed";
        }
    } catch (e) {
        errorEl.innerText = "Network error: " + e;
    }
}

function handleLogout() {
    localStorage.removeItem('user_token');
    localStorage.removeItem('user_name');
    currentUserToken = null;
    currentUsername = null;
    document.getElementById('chatbox').innerHTML = `
        <div class="message ai welcome-message">
            👋 Welcome to Stock AI Assistant! Please log in first.
        </div>
    `;
    checkLoginStatus();
}

async function clearHistory() {
    if (!currentUserToken) return;
    if (!confirm("Are you sure you want to clear your chat history? This action is irreversible.")) return;
    
    try {
        const res = await fetch(`${API_URL}/api/history/clear`, {
            method: 'POST',
            headers: { 'X-Username': currentUserToken }
        });
        if (res.ok) {
            document.getElementById('chatbox').innerHTML = `
                <div class="message ai welcome-message">
                    <div style="font-size: 1.2em; font-weight: bold; margin-bottom: 8px;">🧹 Memory Cleared</div>
                    <div style="color: #555; line-height: 1.6;">
                        All history has been cleared, let's start fresh!
                    </div>
                </div>
            `;
        }
    } catch(e) {
        alert("Failed to clear: " + e);
    }
}

async function loadHistory() {
    if (!currentUserToken) return;
    try {
        const res = await fetch(`${API_URL}/api/history`, {
            headers: { 'X-Username': currentUserToken }
        });
        if (res.ok) {
            const data = await res.json();
            const chatbox = document.getElementById('chatbox');
            chatbox.innerHTML = ''; // clear view
            if (data.chats && data.chats.length > 0) {
                data.chats.forEach(chat => {
                    addMessage(chat.user, 'user');
                    addMessage(chat.ai, 'ai');
                });
            } else {
                chatbox.innerHTML = `
                    <div class="message ai welcome-message">
                        <div style="font-size: 1.2em; font-weight: bold; margin-bottom: 8px;">👋 Welcome back, ${currentUsername}！</div>
                        <div style="color: #555; line-height: 1.6;">
                            You can directly enter a stock code or company name for analysis, e.g.:<br>
                            <span class="quick-tag" onclick="document.getElementById('userInput').value='How is Apple's latest earnings report?';">Apple Earnings</span> 
                            <span class="quick-tag" onclick="document.getElementById('userInput').value='Help me analyze Tesla (TSLA)';">Tesla Trend</span> 
                            <span class="quick-tag" onclick="document.getElementById('userInput').value='0700.HK How is Tencent performing?';">Tencent Holdings</span><br>
                            <span class="quick-tag" onclick="document.getElementById('userInput').value='How is the S&P 500 trend today?';">S&P 500 Trend</span><br>
                            <div style="margin-top: 12px; font-size: 0.9em; border-top: 1px solid #ddd; padding-top: 8px;">
                                💡 <a href="javascript:void(0)" onclick="clearHistory()" style="color: #ff4d4f; text-decoration: none;">Click here to clear my chat memory</a>
                            </div>
                        </div>
                    </div>
                `;
            }
        }
    } catch(e) {
        console.error("Failed to load history", e);
    }
}

async function sendMessage() {
    if (!currentUserToken) {
        alert("Please login first");
        return;
    }
    const input = document.getElementById('userInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Show user message
    addMessage(message, 'user');
    input.value = '';
    input.focus();
    
    const uniqueId = Date.now() + '-' + Math.floor(Math.random() * 10000);
    // Show loading state
    const loadingHtml = `
        <div class="loading-container">
            <div class="spinner"></div>
            <span id="stream-status-${uniqueId}">🚀 Connecting to AI...</span>
        </div>
    `;
    const loadingId = addMessage(loadingHtml, 'ai', 'loading', true, uniqueId);
    
    const msgNode = document.getElementById(`msg-${loadingId}`);
    const statusNode = document.getElementById(`stream-status-${uniqueId}`);
    
    try {
        const response = await fetch(`${API_URL}/api/chat`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-Username': currentUserToken
            },
            body: JSON.stringify({ message })
        });
        
        if (!response.ok) {
            throw new Error('Network request failed, please try again');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        let aiText = '';
        let chartOptions = null;
        let isFirstChunk = true;
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                // 读取完毕，如果还有剩余缓冲区可以处理，不过普通SSE \n\n 结尾无需处理
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            let i;
            while ((i = buffer.indexOf('\n\n')) >= 0) {
                const line = buffer.slice(0, i);
                buffer = buffer.slice(i + 2);
                
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.type === 'status') {
                            if (statusNode) statusNode.innerText = data.message;
                        } else if (data.type === 'chart') {
                            chartOptions = JSON.parse(data.options);
                        } else if (data.type === 'chunk') {
                            if (isFirstChunk) {
                                // Convert to normal bubble
                                msgNode.className = 'message ai';
                                msgNode.innerHTML = '';
                                isFirstChunk = false;
                            }
                            aiText += data.content;
                            msgNode.innerHTML = marked.parse(aiText);
                            
                            // Keep scroll at bottom
                            const chatbox = document.getElementById('chatbox');
                            chatbox.scrollTop = chatbox.scrollHeight;
                        } else if (data.type === 'done') {
                            // Render charts if any
                            if (chartOptions) {
                                const chartDiv = document.createElement('div');
                                chartDiv.className = 'chart-container';
                                msgNode.appendChild(chartDiv);
                                
                                setTimeout(() => {
                                    const chatbox = document.getElementById('chatbox');
                                    chatbox.scrollTop = chatbox.scrollHeight;
                                    const chart = echarts.init(chartDiv);
                                    chart.setOption(chartOptions);
                                    window.addEventListener('resize', () => chart.resize());
                                }, 100);
                            }
                        } else if (data.type === 'error') {
                            msgNode.className = 'message ai error-msg';
                            msgNode.innerHTML = `❌ Error occurred: ${data.message}`;
                        }
                    } catch (err) {
                        console.error('SSE data parse error:', err, '数据:', line);
                    }
                }
            }
        }
        
    } catch (error) {
        msgNode.className = 'message ai error-msg';
        msgNode.innerHTML = `❌ Error occurred: ${error.message}`;
    }
}

function addMessage(text, role, className = '', isHtml = false, forcedId = null) {
    const chatbox = document.getElementById('chatbox');
    const div = document.createElement('div');
    // Prevent ID conflict
    const uniqueId = forcedId || (Date.now() + '-' + Math.floor(Math.random() * 10000));
    const msgId = `msg-${uniqueId}`;
    
    div.id = msgId;
    div.className = `message ${role} ${className}`;
    
    if (isHtml) {
        div.innerHTML = text;
    } else if (role === 'ai' && typeof marked !== 'undefined') {
        // Markdown support
        div.innerHTML = marked.parse(text);
    } else {
        div.textContent = text;
    }
    
    chatbox.appendChild(div);
    
    // Scroll to bottom
    setTimeout(() => {
        chatbox.scrollTop = chatbox.scrollHeight;
    }, 0);
    
    return uniqueId;
}

// Page loaded
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('userInput');
    input.focus();
});