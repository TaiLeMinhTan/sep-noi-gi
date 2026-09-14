let homeData = null;
let currentLesson = null;
let currentLessonId = null;
let currentStep = 0;


function $(id) {
    return document.getElementById(id);
}


function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent =
        String(value ?? "");

    return div.innerHTML;
}


function lessonIdOf(item) {

    return (
        item?.lesson_id
        ?? item?.id
        ?? item?.lesson?.id
        ?? null
    );
}


function getPatterns(item) {

    if (
        Array.isArray(
            item?.highlights
        )
    ) {
        return item.highlights;
    }


    if (
        Array.isArray(
            item?.patterns
        )
    ) {

        return item.patterns
            .map(
                pattern => {

                    if (
                        typeof pattern
                        === "string"
                    ) {

                        return pattern;
                    }

                    return (
                        pattern?.pattern
                        || ""
                    );

                }
            )
            .filter(Boolean);
    }


    return [];
}


async function readJsonResponse(
    response
) {

    const text =
        await response.text();


    if (!text) {
        return {};
    }


    try {

        return JSON.parse(
            text
        );

    }
    catch {

        return {
            raw_response:
                text
        };
    }
}


/* =====================================================
   DEBUG
===================================================== */

function showDebugError(error) {

    const overlay =
        $("debugErrorOverlay");


    const textarea =
        $("debugErrorText");


    if (
        !overlay
        || !textarea
    ) {
        return;
    }


    try {

        textarea.value =
            typeof error === "string"
                ? error
                : JSON.stringify(
                    error,
                    null,
                    2
                );

    }
    catch {

        textarea.value =
            String(error);
    }


    overlay.classList.remove(
        "hidden"
    );
}


function closeDebugError() {

    $("debugErrorOverlay")
        ?.classList
        .add(
            "hidden"
        );
}


async function copyDebugError() {

    const text =
        $("debugErrorText")
            ?.value
        || "";


    try {

        await navigator
            .clipboard
            .writeText(
                text
            );

    }
    catch {

        const textarea =
            $("debugErrorText");


        textarea?.select();


        document.execCommand(
            "copy"
        );
    }


    alert(
        "Error copied."
    );
}


/* =====================================================
   HOME
===================================================== */

async function loadHome() {

    try {

        const response =
            await fetch(
                "/api/home"
            );


        const data =
            await readJsonResponse(
                response
            );


        if (!response.ok) {

            throw data;
        }


        homeData =
            data;


        renderHome(
            data
        );

    }
    catch (error) {

        showDebugError({
            location:
                "GET /api/home",

            error:
                error
        });
    }
}


function renderHome(data) {

    const lessons =
        Array.isArray(data.lessons)
            ? data.lessons
            : [];

    const today =
        lessons.slice(0, 2);

    const reviews =
        (
            Array.isArray(data.reviews)
                ? data.reviews
                : lessons.slice(2, 4)
        )
        .slice(0, 2);

    const stats =
        data.stats
        || {};

    renderTodayLessons(today);
    renderReviews(reviews);

    const goal =
        Number(stats.goal || 2);

    const completed =
        Math.min(
            Number(stats.learned_today || 0),
            goal
        );

    updateTodayProgress(completed, goal);

    const remaining =
        Math.max(0, goal - completed);

    const status =
        completed >= goal
            ? "Done for today"
            : completed === 0
                ? "Ready to learn"
                : "Keep going";

    setText("todayStatus", status);

    setText(
        "todayHint",
        completed >= goal
            ? "Come back tomorrow"
            : `${remaining} sentence${remaining > 1 ? "s" : ""} left`
    );

    renderWeekDots(
        Array.isArray(stats.week_days)
            ? stats.week_days
            : []
    );
}


/* =====================================================
   TODAY CIRCLE
===================================================== */

function updateTodayProgress(
    completed,
    target
) {

    target =
        Number(
            target
            || 2
        );


    if (
        !Number.isFinite(target)
        || target <= 0
    ) {

        target = 2;
    }


    completed =
        Number(
            completed
            || 0
        );


    if (
        !Number.isFinite(completed)
        || completed < 0
    ) {

        completed = 0;
    }


    completed =
        Math.min(
            completed,
            target
        );


    setText(
        "todayGoalNumber",
        completed
    );


    const ring =
        $("goalRing");


    if (ring) {

        const percentage =
            Math.min(
                100,
                Math.max(
                    0,
                    (
                        completed
                        / target
                    )
                    * 100
                )
            );


        ring.style.setProperty(
            "--goal",
            `${percentage}%`
        );


        ring.setAttribute(
            "aria-label",
            `${completed} of ${target} sentences completed today`
        );
    }
}


/* =====================================================
   TODAY LESSONS
===================================================== */

function renderTodayLessons(
    lessons
) {

    const container =
        $("todayLessons");


    if (!container) {
        return;
    }


    lessons =
        Array.isArray(
            lessons
        )
            ? lessons.slice(
                0,
                2
            )
            : [];


    if (!lessons.length) {

        container.innerHTML = `
            <div class="empty-soft">
                Add your first useful sentence today.
            </div>
        `;

        return;
    }


    container.innerHTML =
        lessons.map(
            (
                item,
                index
            ) => {

                const id =
                    lessonIdOf(
                        item
                    );


                const sentence =
                    item.sentence
                    || item.original_text
                    || "";


                const patterns =
                    getPatterns(
                        item
                    )
                    .slice(
                        0,
                        2
                    );


                const image =
                    item.image_url
                    || item.visual_url
                    || item.image_path
                    || item.visual_asset?.image_path
                    || "";


                return `
                    <article
                        class="today-card"
                        onclick="openLesson(${Number(id)})"
                    >

                        <div class="today-card-visual">

                            ${
                                image

                                ? `
                                    <img
                                        src="${escapeHtml(image)}"
                                        alt="Visual for ${escapeHtml(sentence)}"
                                    >
                                `

                                : `
                                    <div class="today-card-visual-placeholder">
                                        Open the lesson to create
                                        or load its visual.
                                    </div>
                                `
                            }

                        </div>


                        <div class="today-card-content">

                            <div class="today-card-number">
                                SENTENCE
                                ${String(index + 1).padStart(2, "0")}
                            </div>


                            <div class="today-card-sentence">
                                ${escapeHtml(sentence)}
                            </div>


                            <div class="today-card-patterns">

                                ${
                                    patterns.map(
                                        pattern => `
                                            <span class="pattern-pill">
                                                ${escapeHtml(pattern)}
                                            </span>
                                        `
                                    )
                                    .join("")
                                }

                            </div>

                        </div>

                    </article>
                `;

            }
        )
        .join("");
}


/* =====================================================
   REVIEW
===================================================== */

function renderReviews(
    reviews
) {

    const container =
        $("reviewList");


    const count =
        $("reviewCount");


    if (
        !container
        || !count
    ) {
        return;
    }


    reviews =
        Array.isArray(
            reviews
        )
            ? reviews.slice(
                0,
                2
            )
            : [];


    count.textContent =
        `${reviews.length} ready`;


    if (!reviews.length) {

        container.innerHTML = `
            <div class="review-empty">
                Nothing to review right now.
            </div>
        `;

        return;
    }


    container.innerHTML =
        reviews.map(
            (
                item,
                index
            ) => {

                const id =
                    lessonIdOf(
                        item
                    );


                const sentence =
                    item.sentence
                    || item.original_text
                    || "";


                const patterns =
                    getPatterns(
                        item
                    )
                    .slice(
                        0,
                        2
                    );


                return `
                    <button
                        class="review-card"
                        type="button"
                        onclick="openLesson(${Number(id)})"
                    >

                        <div class="review-number">
                            ${String(index + 1).padStart(2, "0")}
                        </div>


                        <div class="review-main">

                            <div class="review-sentence">
                                ${escapeHtml(sentence)}
                            </div>


                            <div class="review-patterns">

                                ${
                                    patterns.map(
                                        pattern => `
                                            <span>
                                                ${escapeHtml(pattern)}
                                            </span>
                                        `
                                    )
                                    .join("")
                                }

                            </div>

                        </div>


                        <div class="review-action">
                            Review →
                        </div>

                    </button>
                `;

            }
        )
        .join("");
}


/* =====================================================
   CREATE LESSON
===================================================== */

async function createLesson() {

    const input =
        $("newSentenceInput");


    const button =
        $("createLessonButton");


    const status =
        $("createLessonStatus");


    const sentence =
        input?.value.trim()
        || "";


    if (!sentence) {

        input?.focus();

        return;
    }


    button.disabled =
        true;


    status.textContent =
        "Preparing your lesson...";


    try {

        const response =
            await fetch(
                "/api/lessons",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            sentence:
                                sentence
                        })
                }
            );


        const data =
            await readJsonResponse(
                response
            );


        if (!response.ok) {

            throw {
                endpoint:
                    "POST /api/lessons",

                status:
                    response.status,

                response:
                    data
            };
        }


        input.value =
            "";


        status.textContent =
            data.cache_hit
                ? "Loaded from cache."
                : "Lesson created.";


        const id =
            lessonIdOf(
                data.lesson
                || data
            );


        if (id) {

            await openLesson(
                id
            );

        }
        else {

            await loadHome();
        }

    }
    catch (error) {

        status.textContent =
            "Could not create lesson.";


        showDebugError(
            error
        );

    }
    finally {

        button.disabled =
            false;
    }
}


/* =====================================================
   OPEN LESSON
===================================================== */

async function openLesson(
    lessonId
) {

    if (!lessonId) {
        return;
    }


    try {

        const response =
            await fetch(
                `/api/lesson/${lessonId}`
            );


        const data =
            await readJsonResponse(
                response
            );


        if (!response.ok) {

            throw {
                endpoint:
                    `GET /api/lesson/${lessonId}`,

                status:
                    response.status,

                response:
                    data
            };
        }


        currentLesson =
            data.lesson
            || data;


        currentLessonId =
            lessonId;


        renderLesson(
            currentLesson
        );


        $("mainHeader")
            ?.classList
            .add(
                "hidden"
            );


        $("homePage")
            ?.classList
            .add(
                "hidden"
            );


        $("lessonPage")
            ?.classList
            .remove(
                "hidden"
            );


        document.body.style.overflow =
            "hidden";


        goToStep(
            0,
            false
        );


        loadVisual(
            lessonId
        );

    }
    catch (error) {

        showDebugError(
            error
        );
    }
}


/* =====================================================
   RENDER LESSON
===================================================== */

function renderLesson(
    lesson
) {

    const sentence =
        lesson.sentence
        || lesson.original_text
        || "";


    const highlights =
        Array.isArray(
            lesson.highlights
        )
            ? lesson.highlights
            : getPatterns(
                lesson
            );


    setText(
        "seeSentence",
        sentence
    );


    setText(
        "hearSentence",
        sentence
    );


    setText(
        "pronunciationText",
        lesson.pronunciation
        || ""
    );


    renderHighlightPills(
        highlights
    );


    renderNoticeSentence(
        sentence,
        highlights
    );


    renderPatterns(
        lesson.patterns
        || []
    );


    renderUses(
        lesson.uses
        || []
    );


    renderQuiz(
        lesson.quiz
        || [],
        Number(
            lesson.answer
            ?? 0
        )
    );


    setText(
        "turnPrompt",
        lesson.turn_prompt
        || "Use today's pattern in a new sentence."
    );


    if (
        $("turnInput")
    ) {

        $("turnInput").value =
            "";
    }


    $("turnAnswer")
        ?.classList
        .add(
            "hidden"
        );


    $("lessonCompleteBox")
        ?.classList
        .add(
            "hidden"
        );
}


function setText(
    id,
    text
) {

    const element =
        $(id);


    if (element) {

        element.textContent =
            text ?? "";
    }
}


/* =====================================================
   SEE
===================================================== */

function renderHighlightPills(
    items
) {

    const container =
        $("seeHighlights");


    if (!container) {
        return;
    }


    container.innerHTML =
        (items || [])
            .slice(
                0,
                3
            )
            .map(
                item => `
                    <span>
                        ${escapeHtml(item)}
                    </span>
                `
            )
            .join("");
}


/* =====================================================
   NOTICE
===================================================== */

function renderNoticeSentence(
    sentence,
    highlights
) {

    let html =
        escapeHtml(
            sentence
        );


    (highlights || [])
        .forEach(
            highlight => {

                if (!highlight) {
                    return;
                }


                const safe =
                    escapeHtml(
                        highlight
                    );


                html =
                    html.replace(
                        safe,
                        `
                            <span class="highlight-text">
                                ${safe}
                            </span>
                        `
                    );

            }
        );


    if (
        $("noticeSentence")
    ) {

        $("noticeSentence").innerHTML =
            html;
    }
}


/* =====================================================
   PATTERN
===================================================== */

function renderPatterns(
    patterns
) {

    const container =
        $("patternsContainer");


    if (!container) {
        return;
    }


    if (
        !Array.isArray(patterns)
        || !patterns.length
    ) {

        container.innerHTML =
            "";

        return;
    }


    container.innerHTML =
        patterns.map(
            (
                item,
                index
            ) => {

                const name =
                    typeof item
                    === "string"
                        ? item
                        : item.pattern;


                const examples =
                    Array.isArray(
                        item?.examples
                    )
                        ? item.examples
                        : [];


                return `
                    <div
                        class="pattern-card"
                        id="patternCard${index}"
                    >

                        <button
                            class="pattern-button"
                            type="button"
                            onclick="togglePattern(${index})"
                        >

                            <span>
                                ${escapeHtml(name)}
                            </span>

                            <span>
                                ＋
                            </span>

                        </button>


                        <div class="pattern-examples">

                            ${
                                examples.map(
                                    example => `
                                        <div class="pattern-example">
                                            ${escapeHtml(example)}
                                        </div>
                                    `
                                )
                                .join("")
                            }

                        </div>

                    </div>
                `;

            }
        )
        .join("");
}


function togglePattern(
    index
) {

    $(
        `patternCard${index}`
    )
    ?.classList
    .toggle(
        "open"
    );
}


/* =====================================================
   USE
===================================================== */

function renderUses(
    uses
) {

    const container =
        $("usesContainer");


    if (!container) {
        return;
    }


    container.innerHTML =
        (
            Array.isArray(
                uses
            )
                ? uses
                : []
        )
        .map(
            item => `
                <div class="use-item">
                    ${escapeHtml(item)}
                </div>
            `
        )
        .join("");
}


/* =====================================================
   QUIZ
===================================================== */

function renderQuiz(
    options,
    answer
) {

    const container =
        $("quizOptions");


    const feedback =
        $("quizFeedback");


    if (
        !container
        || !feedback
    ) {
        return;
    }


    feedback.textContent =
        "";


    container.innerHTML =
        (
            Array.isArray(
                options
            )
                ? options
                : []
        )
        .map(
            (
                option,
                index
            ) => `
                <button
                    class="quiz-option"
                    id="quizOption${index}"
                    type="button"
                    onclick="chooseQuiz(${index}, ${answer})"
                >
                    ${escapeHtml(option)}
                </button>
            `
        )
        .join("");
}


function chooseQuiz(
    selected,
    correct
) {

    document
        .querySelectorAll(
            ".quiz-option"
        )
        .forEach(
            button => {

                button.classList.remove(
                    "correct",
                    "wrong"
                );

            }
        );


    const feedback =
        $("quizFeedback");


    if (
        selected
        === correct
    ) {

        $(
            `quizOption${selected}`
        )
        ?.classList
        .add(
            "correct"
        );


        feedback.textContent =
            "✓ That sounds natural.";

    }
    else {

        $(
            `quizOption${selected}`
        )
        ?.classList
        .add(
            "wrong"
        );


        $(
            `quizOption${correct}`
        )
        ?.classList
        .add(
            "correct"
        );


        feedback.textContent =
            "Look at the natural option again.";
    }
}


/* =====================================================
   YOUR TURN
===================================================== */

function checkYourTurn() {

    const input =
        $("turnInput");


    if (
        !input
        ?.value
        .trim()
    ) {

        input?.focus();

        return;
    }


    const answer =
        $("turnAnswer");


    answer.innerHTML = `
        <strong>
            One natural answer:
        </strong>

        <div style="margin-top:7px">
            ${
                escapeHtml(
                    currentLesson
                        ?.turn_answer
                    || ""
                )
            }
        </div>
    `;


    answer.classList.remove(
        "hidden"
    );


    $("lessonCompleteBox")
        ?.classList
        .remove(
            "hidden"
        );
}


/* =====================================================
   IMAGE
===================================================== */

async function loadVisual(
    lessonId
) {

    const loading =
        $("visualLoading");


    const image =
        $("lessonVisual");


    const fallback =
        $("visualFallback");


    loading
        ?.classList
        .remove(
            "hidden"
        );


    image
        ?.classList
        .add(
            "hidden"
        );


    fallback
        ?.classList
        .add(
            "hidden"
        );


    try {

        /* CHECK CACHE FIRST */

        let response =
            await fetch(
                `/api/lesson/${lessonId}/visual`
            );


        let data =
            await readJsonResponse(
                response
            );


        let url =
            data.image_url
            || data.visual_url
            || data.image_path;


        if (
            response.ok
            && url
        ) {

            showLessonImage(
                url
            );

            return;
        }


        /* GENERATE ONLY ON CACHE MISS */

        response =
            await fetch(
                `/api/lesson/${lessonId}/visual`,
                {
                    method:
                        "POST"
                }
            );


        data =
            await readJsonResponse(
                response
            );


        if (!response.ok) {

            throw {
                endpoint:
                    `POST /api/lesson/${lessonId}/visual`,

                status:
                    response.status,

                response:
                    data
            };
        }


        url =
            data.image_url
            || data.visual_url
            || data.image_path;


        if (!url) {

            throw {
                message:
                    "Visual API returned no accepted image.",

                response:
                    data
            };
        }


        showLessonImage(
            url
        );

    }
    catch (error) {

        loading
            ?.classList
            .add(
                "hidden"
            );


        fallback
            ?.classList
            .remove(
                "hidden"
            );


        showDebugError(
            error
        );
    }
}


function showLessonImage(
    url
) {

    const loading =
        $("visualLoading");


    const image =
        $("lessonVisual");


    const fallback =
        $("visualFallback");


    if (!image) {
        return;
    }


    image.onload =
        () => {

            loading
                ?.classList
                .add(
                    "hidden"
                );


            fallback
                ?.classList
                .add(
                    "hidden"
                );


            image.classList.remove(
                "hidden"
            );
        };


    image.onerror =
        () => {

            loading
                ?.classList
                .add(
                    "hidden"
                );


            fallback
                ?.classList
                .remove(
                    "hidden"
                );
        };


    image.src =
        url;
}


/* =====================================================
   SPEECH
===================================================== */

function speakCurrentSentence() {

    const sentence =
        currentLesson
            ?.sentence
        || "";


    if (
        !sentence
        || !(
            "speechSynthesis"
            in window
        )
    ) {
        return;
    }


    speechSynthesis.cancel();


    const utterance =
        new SpeechSynthesisUtterance(
            sentence
        );


    utterance.lang =
        "en-US";


    utterance.rate =
        0.9;


    speechSynthesis.speak(
        utterance
    );
}


/* =====================================================
   LESSON NAVIGATION
===================================================== */

function goToStep(
    index,
    smooth = true
) {

    index =
        Math.max(
            0,
            Math.min(
                4,
                index
            )
        );


    const step =
        $(
            `lessonStep${index}`
        );


    if (!step) {
        return;
    }


    step.scrollIntoView({
        behavior:
            smooth
                ? "smooth"
                : "auto",

        block:
            "start"
    });


    updateProgress(
        index
    );
}


function updateProgress(
    index
) {

    currentStep =
        index;


    document
        .querySelectorAll(
            ".lesson-dot"
        )
        .forEach(
            (
                dot,
                dotIndex
            ) => {

                dot.classList.remove(
                    "active",
                    "done"
                );


                if (
                    dotIndex
                    < index
                ) {

                    dot.classList.add(
                        "done"
                    );

                }
                else if (
                    dotIndex
                    === index
                ) {

                    dot.classList.add(
                        "active"
                    );
                }

            }
        );
}


function setupLessonObserver() {

    const scroller =
        $("lessonScroller");


    if (!scroller) {
        return;
    }


    const observer =
        new IntersectionObserver(
            entries => {

                entries.forEach(
                    entry => {

                        if (
                            !entry.isIntersecting
                        ) {
                            return;
                        }


                        entry.target
                            .classList
                            .add(
                                "is-visible"
                            );


                        updateProgress(
                            Number(
                                entry
                                    .target
                                    .dataset
                                    .step
                            )
                        );

                    }
                );

            },
            {
                root:
                    scroller,

                threshold:
                    0.55
            }
        );


    document
        .querySelectorAll(
            ".lesson-step"
        )
        .forEach(
            step => {

                observer.observe(
                    step
                );

            }
        );
}


/* =====================================================
   COMPLETE
===================================================== */

async function completeLesson() {

    if (!currentLessonId) {

        goHome();

        return;
    }


    try {

        const response =
            await fetch(
                `/api/lesson/${currentLessonId}/complete`,
                {
                    method:
                        "POST"
                }
            );


        const data =
            await readJsonResponse(
                response
            );


        if (!response.ok) {

            throw {
                endpoint:
                    `POST /api/lesson/${currentLessonId}/complete`,

                status:
                    response.status,

                response:
                    data
            };
        }


        goHome();


        await loadHome();

    }
    catch (error) {

        showDebugError(
            error
        );
    }
}


/* =====================================================
   HOME
===================================================== */

function goHome() {

    $("lessonPage")
        ?.classList
        .add(
            "hidden"
        );


    $("homePage")
        ?.classList
        .remove(
            "hidden"
        );


    $("mainHeader")
        ?.classList
        .remove(
            "hidden"
        );


    document.body.style.overflow =
        "";


    currentLesson =
        null;


    currentLessonId =
        null;


    window.scrollTo({
        top:0,
        behavior:"smooth"
    });
}


/* =====================================================
   START
===================================================== */
function renderWeekDots(days) {

    const container =
        $("weekDots");

    if (!container) {
        return;
    }

    const completed =
        days.filter(
            day => day.done
        ).length;

    setText(
        "weekCompleted",
        `${completed}/7`
    );

    container.innerHTML =
        days.map(
            day => `
                <span
                    class="week-dot ${day.done ? "is-done" : ""}"
                    aria-label="${day.date}: ${day.done ? "completed" : "not completed"}"
                ></span>
            `
        )
        .join("");
}


function refreshHomeAtMidnight() {

    const now =
        new Date();

    const nextMidnight =
        new Date(
            now.getFullYear(),
            now.getMonth(),
            now.getDate() + 1,
            0, 0, 2
        );

    window.setTimeout(
        async () => {
            await loadHome();
            refreshHomeAtMidnight();
        },
        nextMidnight.getTime() - now.getTime()
    );
}

document.addEventListener(
    "DOMContentLoaded",
    () => {

        setupLessonObserver();
        loadHome();
        refreshHomeAtMidnight();

        document.addEventListener(
            "visibilitychange",
            () => {
                if (!document.hidden) {
                    loadHome();
                }
            }
        );
    }
);