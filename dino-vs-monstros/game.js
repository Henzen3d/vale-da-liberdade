const COLS = 9;
const ROWS = 5;

// Configurações do jogo
const DINO_TYPES = {
    triceratops: { cost: 50, hp: 120, maxHp: 120, damage: 20, fireRate: 1500, emoji: '🦕', unlockScore: 0, projectile: true },
    velociraptor: { cost: 100, hp: 80, maxHp: 80, damage: 35, fireRate: 800, emoji: '🦖', unlockScore: 500, projectile: true },
    trex: { cost: 250, hp: 300, maxHp: 300, damage: 80, fireRate: 2000, emoji: '🐉', unlockScore: 1500, projectile: true }
};

const MONSTER_TYPES = [
    { hp: 100, maxHp: 100, speed: 15, damage: 10, emoji: '👾', reward: 10, score: 50 },
    { hp: 200, maxHp: 200, speed: 10, damage: 20, emoji: '👹', reward: 20, score: 100 },
    { hp: 500, maxHp: 500, speed: 8, damage: 40, emoji: '👿', reward: 50, score: 300 }
];

// Estado do Jogo
let state = {
    meat: 100, // Começa com 100 para o primeiro dino
    score: 0,
    wave: 1,
    gameOver: false,
    selectedDino: 'triceratops',
    lastTime: 0,
    spawnTimer: 0,
    meatTimer: 0,
    cellWidth: 0,
    cellHeight: 0
};

// Listas de entidades
let dinosaurs = [];
let monsters = [];
let projectiles = [];

// Elementos da DOM
const meatEl = document.getElementById('meat-count');
const scoreEl = document.getElementById('score-count');
const waveEl = document.getElementById('wave-count');
const battlefieldEl = document.getElementById('battlefield');
const cards = document.querySelectorAll('.dino-card');

// Inicialização
function init() {
    createGrid();
    setupEvents();
    requestAnimationFrame(gameLoop);
}

function createGrid() {
    battlefieldEl.innerHTML = '';
    for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
            const cell = document.createElement('div');
            cell.classList.add('grid-cell');
            cell.dataset.row = r;
            cell.dataset.col = c;
            
            cell.addEventListener('click', () => placeDinosaur(r, c));
            battlefieldEl.appendChild(cell);
        }
    }
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
}

function updateDimensions() {
    const rect = battlefieldEl.getBoundingClientRect();
    state.cellWidth = rect.width / COLS;
    state.cellHeight = rect.height / ROWS;
}

function setupEvents() {
    cards.forEach(card => {
        card.addEventListener('click', () => {
            if (card.classList.contains('locked')) return;
            
            cards.forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            state.selectedDino = card.dataset.type;
        });
    });

    document.getElementById('restart-btn').addEventListener('click', () => {
        location.reload();
    });
}

function placeDinosaur(row, col) {
    if (state.gameOver) return;

    // Verifica se já tem dino na célula
    if (dinosaurs.some(d => d.row === row && d.col === col)) return;

    const dinoInfo = DINO_TYPES[state.selectedDino];
    if (state.meat >= dinoInfo.cost) {
        state.meat -= dinoInfo.cost;
        updateUI();

        const dinoEl = document.createElement('div');
        dinoEl.classList.add('entity', 'dinosaur');
        dinoEl.innerHTML = `
            <span class="emoji">${dinoInfo.emoji}</span>
            <div class="health-bar-container">
                <div class="health-bar"></div>
            </div>
        `;
        
        // Posição baseada no grid
        dinoEl.style.left = `${col * state.cellWidth}px`;
        dinoEl.style.top = `${row * state.cellHeight}px`;
        dinoEl.style.width = `${state.cellWidth}px`;
        dinoEl.style.height = `${state.cellHeight}px`;
        
        battlefieldEl.appendChild(dinoEl);

        dinosaurs.push({
            type: state.selectedDino,
            row, col,
            x: col * state.cellWidth,
            y: row * state.cellHeight,
            hp: dinoInfo.hp,
            maxHp: dinoInfo.maxHp,
            damage: dinoInfo.damage,
            fireRate: dinoInfo.fireRate,
            lastFire: 0,
            el: dinoEl
        });
    }
}

function spawnMonster() {
    const row = Math.floor(Math.random() * ROWS);
    
    // Dificuldade baseada na onda
    let monsterTypeIndex = 0;
    if (state.wave > 2 && Math.random() > 0.7) monsterTypeIndex = 1;
    if (state.wave > 5 && Math.random() > 0.85) monsterTypeIndex = 2;
    
    const mInfo = MONSTER_TYPES[monsterTypeIndex];
    
    const el = document.createElement('div');
    el.classList.add('entity', 'monster', 'walking');
    el.innerHTML = `
        <span class="emoji">${mInfo.emoji}</span>
        <div class="health-bar-container">
            <div class="health-bar"></div>
        </div>
    `;

    const startX = battlefieldEl.clientWidth;
    el.style.left = `${startX}px`;
    el.style.top = `${row * state.cellHeight}px`;
    el.style.width = `${state.cellWidth}px`;
    el.style.height = `${state.cellHeight}px`;

    battlefieldEl.appendChild(el);

    monsters.push({
        row,
        x: startX,
        y: row * state.cellHeight,
        hp: mInfo.hp,
        maxHp: mInfo.maxHp,
        speed: mInfo.speed,
        damage: mInfo.damage,
        reward: mInfo.reward,
        score: mInfo.score,
        lastAttack: 0,
        el: el
    });
}

function checkUnlocks() {
    if (state.score >= DINO_TYPES.velociraptor.unlockScore) {
        const c = document.getElementById('card-velociraptor');
        if(c.classList.contains('locked')) {
            c.classList.remove('locked');
            document.getElementById('lock-velociraptor').style.display = 'none';
        }
    }
    if (state.score >= DINO_TYPES.trex.unlockScore) {
        const c = document.getElementById('card-trex');
        if(c.classList.contains('locked')) {
            c.classList.remove('locked');
            document.getElementById('lock-trex').style.display = 'none';
        }
    }
}

function updateUI() {
    meatEl.innerText = Math.floor(state.meat);
    scoreEl.innerText = state.score;
    waveEl.innerText = `Onda ${state.wave}`;
    checkUnlocks();
}

function triggerDamageVisual(el) {
    el.classList.add('taking-damage');
    setTimeout(() => {
        if(el) el.classList.remove('taking-damage');
    }, 200);
}

function endGame() {
    state.gameOver = true;
    document.getElementById('game-over-modal').classList.remove('hidden');
    document.getElementById('final-score').innerText = state.score;
}

// Lógica principal de atualização (Frame)
function update(dt, time) {
    if (state.gameOver) return;

    // Geração passiva de Carne (2 por segundo)
    state.meatTimer += dt;
    if (state.meatTimer > 1000) {
        state.meat += 2;
        state.meatTimer = 0;
        updateUI();
    }

    // Geração de Monstros
    // Tempo diminui conforme a onda aumenta
    const spawnInterval = Math.max(1500, 5000 - (state.wave * 300));
    state.spawnTimer += dt;
    if (state.spawnTimer > spawnInterval) {
        spawnMonster();
        state.spawnTimer = 0;
        
        // Aumenta onda a cada 1000 pontos
        state.wave = Math.floor(state.score / 1000) + 1;
        updateUI();
    }

    // Atualiza Dinossauros (Tiros)
    dinosaurs.forEach(dino => {
        // Encontra o monstro mais próximo na mesma linha
        const target = monsters.find(m => m.row === dino.row && m.x > dino.x);
        
        if (target && target.x - dino.x < state.cellWidth * COLS) {
            if (time - dino.lastFire > dino.fireRate) {
                dino.lastFire = time;
                dino.el.classList.add('attacking');
                setTimeout(() => dino.el.classList.remove('attacking'), 300);

                // Criar projétil
                const projEl = document.createElement('div');
                projEl.classList.add('projectile');
                projEl.style.left = `${dino.x + state.cellWidth/2}px`;
                projEl.style.top = `${dino.y + state.cellHeight/2 - 10}px`;
                battlefieldEl.appendChild(projEl);

                projectiles.push({
                    x: dino.x + state.cellWidth/2,
                    y: dino.y + state.cellHeight/2 - 10,
                    row: dino.row,
                    damage: dino.damage,
                    speed: 300, // px por segundo
                    el: projEl
                });
            }
        }
    });

    // Atualiza Projéteis
    for (let i = projectiles.length - 1; i >= 0; i--) {
        const p = projectiles[i];
        p.x += (p.speed * dt) / 1000;
        p.el.style.left = `${p.x}px`;

        // Colisão com Monstros
        const hitMonster = monsters.find(m => m.row === p.row && Math.abs(m.x - p.x) < 40);
        if (hitMonster) {
            hitMonster.hp -= p.damage;
            triggerDamageVisual(hitMonster.el);
            
            // Atualiza barra de vida
            const pct = Math.max(0, (hitMonster.hp / hitMonster.maxHp) * 100);
            hitMonster.el.querySelector('.health-bar').style.width = `${pct}%`;

            p.el.remove();
            projectiles.splice(i, 1);
        } else if (p.x > battlefieldEl.clientWidth) {
            p.el.remove();
            projectiles.splice(i, 1);
        }
    }

    // Atualiza Monstros (Andar e Atacar)
    for (let i = monsters.length - 1; i >= 0; i--) {
        const m = monsters[i];
        
        // Verifica se morreu
        if (m.hp <= 0) {
            state.score += m.score;
            state.meat += m.reward;
            updateUI();
            m.el.remove();
            monsters.splice(i, 1);
            continue;
        }

        // Verifica colisão com dino
        const hitDino = dinosaurs.find(d => d.row === m.row && Math.abs(d.x - m.x) < state.cellWidth/2);

        if (hitDino) {
            // Ataca
            m.el.classList.remove('walking');
            if (time - m.lastAttack > 1000) {
                m.lastAttack = time;
                hitDino.hp -= m.damage;
                triggerDamageVisual(hitDino.el);

                const pct = Math.max(0, (hitDino.hp / hitDino.maxHp) * 100);
                hitDino.el.querySelector('.health-bar').style.width = `${pct}%`;

                if (hitDino.hp <= 0) {
                    hitDino.el.remove();
                    dinosaurs.splice(dinosaurs.indexOf(hitDino), 1);
                    m.el.classList.add('walking');
                }
            }
        } else {
            // Anda
            m.x -= (m.speed * dt) / 100;
            m.el.style.left = `${m.x}px`;

            // Chegou na base (Game Over)
            if (m.x < -state.cellWidth / 2) {
                endGame();
            }
        }
    }
}

function gameLoop(time) {
    if (!state.lastTime) state.lastTime = time;
    const dt = time - state.lastTime;
    state.lastTime = time;

    update(dt, time);

    if (!state.gameOver) {
        requestAnimationFrame(gameLoop);
    }
}

// Inicia após carregamento
window.addEventListener('load', init);
