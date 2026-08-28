let currentSlideIndex = 0;

function getHistorySliderData() {
    const slider = document.getElementById("history-slider");

    if (!slider) {
        return null;
    }

    return {
        page: parseInt(slider.dataset.page, 10) || 1,
        totalPages: parseInt(slider.dataset.totalPages, 10) || 1,
        perPage: parseInt(slider.dataset.perPage, 10) || 25,
        totalCount: parseInt(slider.dataset.totalCount, 10) || 0
    };
}


function showSlide(index) {
    const slides = document.querySelectorAll(".slide-card");
    const counter = document.getElementById("slide-counter");
    const previewItems = document.querySelectorAll(".card-preview-item");
    const historyData = getHistorySliderData();

    if (slides.length === 0 || !historyData) {
        return;
    }

    /*
     * Unlike the old generic slider, History does not wrap around
     * inside the current batch.
     */
    if (index < 0) {
        index = 0;
    }

    if (index >= slides.length) {
        index = slides.length - 1;
    }

    currentSlideIndex = index;

    slides.forEach(function(slide, slideIndex) {
        slide.style.display =
            slideIndex === currentSlideIndex ? "block" : "none";
    });

    previewItems.forEach(function(item, itemIndex) {
        if (itemIndex === currentSlideIndex) {
            item.classList.add("active-preview-item");
        } else {
            item.classList.remove("active-preview-item");
        }
    });

    if (counter) {
        const globalPosition =
            ((historyData.page - 1) * historyData.perPage)
            + currentSlideIndex
            + 1;

        counter.textContent =
            globalPosition + " / " + historyData.totalCount;
    }
}


function navigateToHistoryBatch(page, slide) {
    const url = new URL(window.location.href);

    /*
     * Modifying the existing URL preserves all current History
     * filters and sorting options.
     */
    url.searchParams.set("page", page);

    if (slide === "last") {
        url.searchParams.set("slide", "last");
    } else {
        url.searchParams.set("slide", String(slide));
    }

    window.location.assign(url.toString());
}


function nextSlide(event) {
    if (event) {
        event.preventDefault();
    }

    const slides = document.querySelectorAll(".slide-card");
    const historyData = getHistorySliderData();

    if (slides.length === 0 || !historyData) {
        return;
    }

    /*
     * Still inside the current 25-record batch:
     * navigation is instant and requires no server request.
     */
    if (currentSlideIndex < slides.length - 1) {
        showSlide(currentSlideIndex + 1);
        return;
    }

    /*
     * End of this batch:
     * fetch the next batch and start at its first record.
     */
    if (historyData.page < historyData.totalPages) {
        navigateToHistoryBatch(historyData.page + 1, 0);
    }
}


function previousSlide(event) {
    if (event) {
        event.preventDefault();
    }

    const historyData = getHistorySliderData();

    if (!historyData) {
        return;
    }

    if (currentSlideIndex > 0) {
        showSlide(currentSlideIndex - 1);
        return;
    }

    /*
     * Beginning of this batch:
     * fetch the previous batch and open its final record.
     */
    if (historyData.page > 1) {
        navigateToHistoryBatch(historyData.page - 1, "last");
    }
}


function firstSlide(event) {
    if (event) {
        event.preventDefault();
    }

    const historyData = getHistorySliderData();

    if (!historyData) {
        return;
    }

    if (historyData.page === 1) {
        showSlide(0);
    } else {
        navigateToHistoryBatch(1, 0);
    }
}


function lastSlide(event) {
    if (event) {
        event.preventDefault();
    }

    const slides = document.querySelectorAll(".slide-card");
    const historyData = getHistorySliderData();

    if (slides.length === 0 || !historyData) {
        return;
    }

    if (historyData.page === historyData.totalPages) {
        showSlide(slides.length - 1);
    } else {
        navigateToHistoryBatch(historyData.totalPages, "last");
    }
}


function jumpToSlide(index, event) {
    if (event) {
        event.preventDefault();
    }

    showSlide(index);
}


document.addEventListener("DOMContentLoaded", function() {
    const slides = document.querySelectorAll(".slide-card");

    if (slides.length === 0) {
        return;
    }

    const params = new URLSearchParams(window.location.search);
    const requestedSlide = params.get("slide");

    if (requestedSlide === "last") {
        showSlide(slides.length - 1);
        return;
    }

    if (requestedSlide !== null) {
        const requestedIndex = parseInt(requestedSlide, 10);

        if (!Number.isNaN(requestedIndex)) {
            showSlide(requestedIndex);
            return;
        }
    }

    showSlide(0);
});