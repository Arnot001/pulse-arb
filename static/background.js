const canvas = document.getElementById("pulse-canvas");

if (canvas) {

    const ctx = canvas.getContext("2d");

    let particles = [];

    const COUNT = 55;
    const SPEED = 0.18;
    const LINK_DISTANCE = 150;

    function resize() {

        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;

    }

    window.addEventListener("resize", resize);
    resize();

    function random(min, max) {
        return Math.random() * (max - min) + min;
    }

    function createParticles() {

        particles = [];

        for (let i = 0; i < COUNT; i++) {

            particles.push({

                x: random(0, canvas.width),
                y: random(0, canvas.height),

                vx: random(-SPEED, SPEED),
                vy: random(-SPEED, SPEED),

                radius: random(1.2, 2.4)

            });

        }

    }

    createParticles();

    function draw() {

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // ---------- Connections ----------

        for (let i = 0; i < particles.length; i++) {

            for (let j = i + 1; j < particles.length; j++) {

                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;

                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < LINK_DISTANCE) {

                    const alpha = (1 - dist / LINK_DISTANCE) * 0.08;

                    ctx.beginPath();

                    ctx.strokeStyle =
                        `rgba(255,255,255,${alpha})`;

                    ctx.lineWidth = 1;

                    ctx.moveTo(
                        particles[i].x,
                        particles[i].y
                    );

                    ctx.lineTo(
                        particles[j].x,
                        particles[j].y
                    );

                    ctx.stroke();

                }

            }

        }

        // ---------- Nodes ----------

        particles.forEach(p => {

            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0 || p.x > canvas.width)
                p.vx *= -1;

            if (p.y < 0 || p.y > canvas.height)
                p.vy *= -1;

            ctx.beginPath();

            ctx.fillStyle =
                "rgba(255,255,255,.18)";

            ctx.arc(
                p.x,
                p.y,
                p.radius,
                0,
                Math.PI * 2
            );

            ctx.fill();

        });

        requestAnimationFrame(draw);

    }

    draw();

}