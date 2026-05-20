let currentSlideIndex = 0;

function showSlide(index) {
    const slides = document.querySelectorAll(".slide-card");
    const counter = document.getElementById("slide-counter");
    const previewItems = document.querySelectorAll(".card-preview-item");

    if (slides.length === 0) {
        return;
    }

    if (index < 0) {
        currentSlideIndex = slides.length - 1;
    } else if (index >= slides.length) {
        currentSlideIndex = 0;
    } else {
        currentSlideIndex = index;
    }

    slides.forEach(function(slide, slideIndex) {
        if (slideIndex === currentSlideIndex) {
            slide.style.display = "block";
        } else {
            slide.style.display = "none";
        }
    });

    previewItems.forEach(function(item, itemIndex) {
        if (itemIndex === currentSlideIndex) {
            item.classList.add("active-preview-item");
        } else {
            item.classList.remove("active-preview-item");
        }
    });

    if (counter) {
        counter.textContent = (currentSlideIndex + 1) + " / " + slides.length;
    }
}

function nextSlide(event) {
    if (event) {
        event.preventDefault();
    }

    showSlide(currentSlideIndex + 1);
}

function previousSlide(event) {
    if (event) {
        event.preventDefault();
    }

    showSlide(currentSlideIndex - 1);
}

function firstSlide(event) {
    if (event) {
        event.preventDefault();
    }

    showSlide(0);
}

function lastSlide(event) {
    if (event) {
        event.preventDefault();
    }

    const slides = document.querySelectorAll(".slide-card");
    showSlide(slides.length - 1);
}

function jumpToSlide(index, event) {
    if (event) {
        event.preventDefault();
    }

    showSlide(index);
}

document.addEventListener("DOMContentLoaded", function() {
    showSlide(0);
});