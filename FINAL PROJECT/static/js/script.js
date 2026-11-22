
/* =========================================
   ANNELSA LUXURY
   Django Dynamic Store JavaScript
========================================= */


/* =========================================
   CONFIGURATION
========================================= */

const ORDER_SETTINGS = window.ORDER_SETTINGS || {};

const WHATSAPP_NUMBER =
    ORDER_SETTINGS.whatsapp_number || "";

const TELEGRAM_USERNAME =
    ORDER_SETTINGS.telegram_username || "";

const PAYMENT_METHOD =
    ORDER_SETTINGS.payment_method || "contact";


/* =========================================
   DJANGO PRODUCT DATA
========================================= */

let productCards = [];

let products = [];

let currentImgIndexes = {};

let activeCategory = "all";


/* =========================================
   LOAD PRODUCTS FROM DJANGO
========================================= */

function loadProducts() {

    productCards =
        Array.from(
            document.querySelectorAll(
                ".product-card[data-product-id]"
            )
        );

    products =
        productCards.map(card => {

            const id =
                Number(
                    card.dataset.productId
                );

            const imageContainer =
                document.getElementById(
                    `images-${id}`
                );

            const images =
                imageContainer
                    ? Array.from(
                        imageContainer.querySelectorAll(
                            "[data-image]"
                        )
                    ).map(
                        item =>
                            item.dataset.image
                    )
                    : [];

            currentImgIndexes[id] = 0;

            return {

                id: id,

                name:
                    card.dataset.productName || "",

                price:
                    Number(
                        card.dataset.productPrice
                    ) || 0,

                category:
                    card.dataset.productCategory || "",

                categoryName:
                    card.dataset.productCategoryName || "",

                description:
                    card.dataset.productDescription || "",

                stock:
                    Number(card.dataset.productStock) || 0,

                images: images

            };

        });

}


/* =========================================
   PRODUCT IMAGE SLIDER
========================================= */

function nextImg(id, event) {

    if (event) {
        event.stopPropagation();
    }

    const product =
        products.find(
            product =>
                product.id === Number(id)
        );

    if (
        !product ||
        product.images.length === 0
    ) {
        return;
    }

    currentImgIndexes[id] =
        (
            currentImgIndexes[id] + 1
        ) %
        product.images.length;

    const image =
        document.getElementById(
            `img-${id}`
        );

    if (image) {

        image.src =
            product.images[
                currentImgIndexes[id]
            ];

    }

}


function prevImg(id, event) {

    if (event) {
        event.stopPropagation();
    }

    const product =
        products.find(
            product =>
                product.id === Number(id)
        );

    if (
        !product ||
        product.images.length === 0
    ) {
        return;
    }

    currentImgIndexes[id] =
        (
            currentImgIndexes[id] -
            1 +
            product.images.length
        ) %
        product.images.length;

    const image =
        document.getElementById(
            `img-${id}`
        );

    if (image) {

        image.src =
            product.images[
                currentImgIndexes[id]
            ];

    }

}


/* =========================================
   SEARCH
========================================= */

let searchInput = null;


function setupSearch() {

    searchInput =
        document.getElementById(
            "search"
        );

    if (searchInput) {

        searchInput.addEventListener(
            "input",
            applyFilters
        );

    }

}


function searchProducts() {

    applyFilters();

}


/* =========================================
   CATEGORY FILTER
========================================= */

function filterProducts(
    category,
    button
) {

    activeCategory =
        category;

    document
        .querySelectorAll(
            ".nav-btn"
        )
        .forEach(btn => {

            btn.classList.remove(
                "active-cat"
            );

        });

    if (button) {

        button.classList.add(
            "active-cat"
        );

    }

    applyFilters();

}


function applyFilters() {

    const query =
        searchInput
            ? searchInput.value
                .trim()
                .toLowerCase()
            : "";

    let visibleProductCount = 0;

    productCards.forEach(card => {

        const name =
            (
                card.dataset.productName || ""
            ).toLowerCase();

        const category =
            (
                card.dataset.productCategory || ""
            ).toLowerCase();

        const categoryMatches =
            activeCategory === "all" ||
            category ===
                activeCategory.toLowerCase();

        const categoryName =
            (
                card.dataset.productCategoryName || ""
            ).toLowerCase();

        const description =
            (
                card.dataset.productDescription || ""
            ).toLowerCase();

        const searchMatches =
            name.includes(query) ||
            categoryName.includes(query) ||
            description.includes(query);

        const isVisible = categoryMatches && searchMatches;
        card.style.display = isVisible ? "" : "none";
        if (isVisible) {
            visibleProductCount += 1;
        }

    });

    const emptyState =
        document.getElementById("productSearchEmptyState");

    if (emptyState) {
        emptyState.hidden =
            query.length === 0 ||
            visibleProductCount > 0;
    }

}


/* =========================================
   SHOPPING CART
========================================= */

let cart = [];


function loadCart() {

    try {
        const savedCart =
            JSON.parse(
                localStorage.getItem("annelsa_cart") || "[]"
            );

        if (!Array.isArray(savedCart)) {
            throw new Error("Saved cart is not a list.");
        }

        return savedCart;

    } catch (error) {
        console.error("Unable to read the saved shopping cart:", error);
        return [];
    }

}


function validateCart() {

    cart = cart.reduce((validItems, item) => {
        if (!item || !Number.isInteger(Number(item.id))) {
            return validItems;
        }

        const product =
            products.find(product => product.id === Number(item.id));
        const quantity = Number(item.quantity);

        if (!product || product.stock < 1 || !Number.isInteger(quantity) || quantity < 1) {
            return validItems;
        }

        const existing =
            validItems.find(validItem => validItem.id === product.id);
        const availableQuantity =
            Math.min(quantity + (existing ? existing.quantity : 0), product.stock);

        if (existing) {
            existing.quantity = availableQuantity;
        } else {
            validItems.push({
                id: product.id,
                name: product.name,
                price: product.price,
                quantity: Math.min(quantity, product.stock)
            });
        }

        return validItems;
    }, []);

    saveCart();

}


function saveCart() {

    localStorage.setItem(
        "annelsa_cart",
        JSON.stringify(cart)
    );

}


/* =========================================
   ADD PRODUCT TO CART
========================================= */

function addToCart(productId) {

    const product =
        products.find(
            product =>
                product.id === Number(productId)
        );

    if (!product) {

        console.error(
            "Product not found:",
            productId
        );

        return;

    }

    if (product.stock < 1) {
        alert("This product is currently out of stock.");
        return;
    }

    const existingItem =
        cart.find(
            item =>
                item.id === product.id
        );

    if (existingItem) {

        if (existingItem.quantity >= product.stock) {
            alert("You have already added all available units of this product.");
            return;
        }

        existingItem.quantity += 1;

    } else {

        cart.push({

            id:
                product.id,

            name:
                product.name,

            price:
                product.price,

            quantity:
                1

        });

    }

    saveCart();

    updateCart();

}


/* =========================================
   REMOVE FROM CART
========================================= */

function removeFromCart(productId) {

    cart =
        cart.filter(
            item =>
                item.id !== Number(productId)
        );

    saveCart();

    updateCart();

}


/* =========================================
   CHANGE CART QUANTITY
========================================= */

function changeQuantity(
    productId,
    amount
) {

    const item =
        cart.find(
            item =>
                item.id === Number(productId)
        );

    if (!item) {
        return;
    }

    const product =
        products.find(product => product.id === Number(productId));

    if (
        amount > 0 &&
        product &&
        item.quantity >= product.stock
    ) {
        alert("You have reached the available stock for this product.");
        return;
    }

    item.quantity += amount;

    if (item.quantity <= 0) {

        removeFromCart(productId);

        return;

    }

    saveCart();

    updateCart();

}


/* =========================================
   UPDATE CART DISPLAY
========================================= */

function updateCart() {

    const cartItems =
        document.getElementById(
            "cartItems"
        );

    const cartCount =
        document.getElementById(
            "cartCount"
        );

    const cartTotal =
        document.getElementById(
            "cartTotal"
        );

    if (!cartItems) {
        return;
    }

    let total = 0;

    let itemCount = 0;


    if (cart.length === 0) {

        cartItems.innerHTML = `

            <p style="color:#aaa;">
                Your shopping bag is empty.
            </p>

        `;

    } else {

        cartItems.innerHTML =
            cart
                .map(item => {

                    const itemTotal =
                        item.price *
                        item.quantity;

                    total +=
                        itemTotal;

                    itemCount +=
                        item.quantity;

                    return `

                        <div class="cart-item">

                            <div>

                                <strong>
                                    ${escapeHtml(
                                        item.name
                                    )}
                                </strong>

                                <p>
                                    ₦${formatMoney(
                                        item.price
                                    )}
                                </p>

                            </div>


                            <div class="cart-controls">

                                <button
                                    type="button"
                                    onclick="changeQuantity(${item.id}, -1)">
                                    −
                                </button>


                                <span>
                                    ${item.quantity}
                                </span>


                                <button
                                    type="button"
                                    onclick="changeQuantity(${item.id}, 1)">
                                    +
                                </button>


                                <button
                                    type="button"
                                    onclick="removeFromCart(${item.id})">
                                    ×
                                </button>

                            </div>


                            <strong>
                                ₦${formatMoney(
                                    itemTotal
                                )}
                            </strong>

                        </div>

                    `;

                })
                .join("");

    }


    if (cartCount) {

        cartCount.textContent =
            itemCount;

    }


    if (cartTotal) {

        cartTotal.textContent =
            `₦${formatMoney(total)}`;

    }

}


/* =========================================
   MONEY FORMAT
========================================= */

function formatMoney(value) {

    return Number(value)
        .toLocaleString(
            "en-NG"
        );

}


/* =========================================
   SECURITY
========================================= */

function escapeHtml(value) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        value;

    return div.innerHTML;

}


/* =========================================
   CART PANEL
========================================= */

function openCart() {

    const panel =
        document.getElementById(
            "cartPanel"
        );

    if (panel) {

        panel.classList.add(
            "cart-open"
        );

    }

}


function closeCart() {

    const panel =
        document.getElementById(
            "cartPanel"
        );

    if (panel) {

        panel.classList.remove(
            "cart-open"
        );

    }

}


/* =========================================
   CART BUTTON
========================================= */

function setupCartButton() {

    const cartButton =
        document.getElementById(
            "cartButton"
        );

    if (cartButton) {

        cartButton.addEventListener(
            "click",
            openCart
        );

    }

}


/* =========================================
   SETTINGS MENU
========================================= */

function toggleSettingsMenu() {

    const menu =
        document.getElementById(
            "settingsMenu"
        );

    if (menu) {

        menu.classList.toggle(
            "settings-open"
        );

    }

}


function closeSettingsMenu() {

    const menu =
        document.getElementById(
            "settingsMenu"
        );

    if (menu) {

        menu.classList.remove(
            "settings-open"
        );

    }

}


/* =========================================
   SETTINGS BUTTON
========================================= */

function setupSettingsButton() {

    const settingsButton =
        document.getElementById(
            "settingsButton"
        );

    if (settingsButton) {

        settingsButton.addEventListener(
            "click",
            function(event) {

                event.stopPropagation();

                toggleSettingsMenu();

            }
        );

    }

}


/* =========================================
   ORDER ONE PRODUCT
========================================= */

function openOrderForProduct(
    productId
) {

    const product =
        products.find(
            product =>
                product.id === Number(productId)
        );

    if (!product) {

        console.error(
            "Product not found:",
            productId
        );

        return;

    }

    if (product.stock < 1) {
        alert("This product is currently out of stock.");
        return;
    }

    cart = [{

        id:
            product.id,

        name:
            product.name,

        price:
            product.price,

        quantity:
            1

    }];

    saveCart();

    updateCart();

    openCart();

}


/* =========================================
   OLD ORDER MODAL
========================================= */

function openModal(name) {

    const encodedText =
        encodeURIComponent(
            `Hello, I would like to order: ${name}`
        );

    const modalName =
        document.getElementById(
            "modalName"
        );

    const whatsappLink =
        document.getElementById(
            "whatsappLink"
        );

    const telegramLink =
        document.getElementById(
            "telegramLink"
        );

    const modal =
        document.getElementById(
            "modal"
        );


    if (modalName) {

        modalName.innerText =
            name;

    }


    if (whatsappLink) {

        whatsappLink.href =
            `https://wa.me/${WHATSAPP_NUMBER}?text=${encodedText}`;

    }


    if (telegramLink) {

        telegramLink.href =
            `https://t.me/${TELEGRAM_USERNAME}?text=${encodedText}`;

    }


    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeModal() {

    const modal =
        document.getElementById(
            "modal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   CHECKOUT
========================================= */

function openCheckout() {

    if (cart.length === 0) {

        const emptyCartModal =
            document.getElementById(
                "emptyCartModal"
            );

        if (emptyCartModal) {

            emptyCartModal.style.display =
                "flex";

        }

        return;

    }


    closeCart();


    const modal =
        document.getElementById(
            "checkoutModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }


    const cartData =
        document.getElementById(
            "cartData"
        );

    if (cartData) {

        cartData.value =
            JSON.stringify(cart);

    }


    setupPaymentMethod();

}


/* =========================================
   PAYMENT METHOD
========================================= */

function setupPaymentMethod() {

    const emailInput =
        document.getElementById(
            "customerEmail"
        );

    const paymentMethod =
        (
            ORDER_SETTINGS.payment_method ||
            PAYMENT_METHOD ||
            "contact"
        ).trim().toLowerCase();


    if (emailInput && paymentMethod === "paystack") {
        emailInput.style.display =
            "block";
        emailInput.required =
            true;
    } else if (emailInput) {
        emailInput.style.display =
            "none";
        emailInput.required =
            false;
        emailInput.value =
            "";
    }

    const contactMethodField =
        document.getElementById("contactMethodField");
    const contactMethodSelect =
        document.getElementById("contactMethod");
    if (contactMethodField) {
        contactMethodField.style.display =
            paymentMethod === "contact" ? "block" : "none";
    }
    if (contactMethodSelect) {
        contactMethodSelect.required =
            paymentMethod === "contact";
    }

}


/* =========================================
   CHECKOUT FORM
========================================= */

function setupCheckoutForm() {

    const form =
        document.getElementById(
            "checkoutForm"
        );

    if (!form) {
        return;
    }


    form.addEventListener(
        "submit",
        async function(event) {

            event.preventDefault();


            if (cart.length === 0) {

                return;

            }


            setupPaymentMethod();


            const cartData =
                document.getElementById(
                    "cartData"
                );

            if (cartData) {

                cartData.value =
                    JSON.stringify(cart);

            }


            const submitButton =
                form.querySelector(
                    'button[type="submit"]'
                );


            if (submitButton) {

                submitButton.disabled =
                    true;

                submitButton.textContent =
                    "Processing...";

            }


            try {

                const formData =
                    new FormData(form);


                const response =
                    await fetch(
                        form.action,
                        {
                            method: "POST",

                            body: formData,

                            headers: {
                                "X-Requested-With":
                                    "XMLHttpRequest"
                            }
                        }
                    );


                const data =
                    await response.json();


                if (
                    !response.ok ||
                    data.status === "error"
                ) {

                    throw new Error(
                        data.message ||
                        "Unable to process your order."
                    );

                }

                if (
                    data.status === "redirect" &&
                    data.redirect_url
                ) {
                    window.location.assign(data.redirect_url);
                    return;
                }


                /* =========================
                   PAYSTACK
                ========================= */

                if (
                    data.status ===
                    "paystack"
                ) {

                    if (
                        data.authorization_url
                    ) {

                        window.location.href =
                            data.authorization_url;

                        return;

                    }

                    throw new Error(
                        "Paystack payment link was not received."
                    );

                }


                /* =========================
                   WHATSAPP / TELEGRAM
                ========================= */

                if (
                    data.status ===
                    "whatsapp_telegram"
                ) {

                    showOrderCommunicationOptions(
                        data
                    );

                    return;

                }


                throw new Error(
                    "Unknown response from the server."
                );

            } catch (error) {

                console.error(
                    "Checkout error:",
                    error
                );


                alert(
                    error.message ||
                    "Something went wrong while creating your order."
                );


                if (submitButton) {

                    submitButton.disabled =
                        false;

                    submitButton.textContent =
                        "Confirm Order";

                }

            }

        }
    );

}


/* =========================================
   WHATSAPP / TELEGRAM ORDER OPTIONS
========================================= */

function showOrderCommunicationOptions(data) {

    const modal =
        document.getElementById(
            "checkoutModal"
        );

    if (!modal) {
        return;
    }


    const modalContent =
        modal.querySelector(
            ".modal-content"
        );

    if (!modalContent) {
        return;
    }


    let buttons = "";


    if (data.whatsapp_url) {

        buttons += `

            <a
                href="${escapeAttribute(
                    data.whatsapp_url
                )}"
                target="_blank"
                rel="noopener noreferrer"
                class="checkout-btn"
                style="display:block;text-align:center;text-decoration:none;margin-bottom:10px;"
            >
                Continue with WhatsApp
            </a>

        `;

    }


    if (data.telegram_url) {

        buttons += `

            <a
                href="${escapeAttribute(
                    data.telegram_url
                )}"
                target="_blank"
                rel="noopener noreferrer"
                class="checkout-btn"
                style="display:block;text-align:center;text-decoration:none;margin-bottom:10px;"
            >
                Continue with Telegram
            </a>

        `;

    }


    modalContent.innerHTML = `

        <h2>
            Order #${escapeHtml(
                String(data.order_id)
            )}
            Created
        </h2>

        <p>
            Your order has been received.
            Please continue through WhatsApp or Telegram
            to complete your order.
        </p>

        ${buttons}

        <button
            type="button"
            onclick="finishOrder()"
            class="close-btn"
        >
            Close
        </button>

    `;

    modal.style.display =
        "flex";

}


/* =========================================
   FINISH WHATSAPP / TELEGRAM ORDER
========================================= */

function finishOrder() {

    cart = [];

    saveCart();

    updateCart();

    closeCheckout();

    window.location.reload();

}


/* =========================================
   ESCAPE ATTRIBUTE
========================================= */

function escapeAttribute(value) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        value;

    return div.innerHTML;

}


/* =========================================
   CLOSE EMPTY CART MODAL
========================================= */

function closeEmptyCartModal() {

    const emptyCartModal =
        document.getElementById(
            "emptyCartModal"
        );

    if (emptyCartModal) {

        emptyCartModal.style.display =
            "none";

    }

}


/* =========================================
   CLOSE CHECKOUT
========================================= */

function closeCheckout() {

    const modal =
        document.getElementById(
            "checkoutModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   PRODUCT RATING
========================================= */

let selectedRating = 0;

let ratingProductId = null;


/* =========================================
   OPEN RATING
========================================= */

function openRating(productId) {

    const product =
        products.find(
            product =>
                product.id === Number(productId)
        );

    if (!product) {

        console.error(
            "Product not found for rating:",
            productId
        );

        return;

    }


    ratingProductId =
        product.id;

    selectedRating =
        0;

    const productIdInput =
        document.getElementById("ratingProductIdInput");
    if (productIdInput) {
        productIdInput.value = product.id;
    }
    const ratingInput =
        document.getElementById("ratingInput");
    if (ratingInput) {
        ratingInput.value = "";
    }
    const ratingForm =
        document.getElementById("ratingForm");
    if (ratingForm) {
        ratingForm.reset();
        if (productIdInput) {
            productIdInput.value = product.id;
        }
    }

    const productName =
        document.getElementById(
            "ratingProductName"
        );

    if (productName) {

        productName.textContent =
            product.name;

    }


    document
        .querySelectorAll(
            ".rating-selector button"
        )
        .forEach(button => {

            button.classList.remove(
                "selected"
            );

        });


    const modal =
        document.getElementById(
            "ratingModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


/* =========================================
   SELECT STAR RATING
========================================= */

function selectRating(rating) {

    selectedRating =
        Number(rating);

    const ratingInput =
        document.getElementById("ratingInput");
    if (ratingInput) {
        ratingInput.value = selectedRating;
    }

    document
        .querySelectorAll(
            ".rating-selector button"
        )
        .forEach(
            (button, index) => {

                button.classList.toggle(
                    "selected",
                    index <
                        selectedRating
                );

            }
        );

}


/* =========================================
   SUBMIT RATING
========================================= */

async function submitRating() {

    const form = document.getElementById("ratingForm");
    if (!form || !ratingProductId || selectedRating < 1) {
        alert("Choose a star rating before submitting.");
        return;
    }

    const submitButton =
        form.querySelector('button[type="submit"]');
    if (submitButton) {
        submitButton.disabled = true;
    }

    try {
        const response = await fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            headers: {"X-Requested-With": "XMLHttpRequest"}
        });
        const result = await response.json();
        if (!response.ok || result.status !== "success") {
            throw new Error(result.message || "Unable to submit your review.");
        }
        form.reset();
        closeRating();
        showRatingThankYou();
    } catch (error) {
        alert(error.message || "Unable to submit your review.");
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
        }
    }

}


/* =========================================
   CLOSE RATING
========================================= */

function closeRating() {

    const modal =
        document.getElementById(
            "ratingModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }


    ratingProductId =
        null;

    selectedRating =
        0;

}


/* =========================================
   RATING THANK YOU
========================================= */

function showRatingThankYou() {

    const modal =
        document.getElementById(
            "ratingThankYouModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeRatingThankYouModal() {

    const modal =
        document.getElementById(
            "ratingThankYouModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   CUSTOMER REVIEWS
========================================= */

function openCustomerReviews() {

    closeSettingsMenu();


    const modal =
        document.getElementById(
            "customerReviewsModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeCustomerReviews() {

    const modal =
        document.getElementById(
            "customerReviewsModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   WRITE A REVIEW
========================================= */

function openWriteReview() {

    closeCustomerReviews();


    const modal =
        document.getElementById(
            "writeReviewModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeWriteReview() {

    const modal =
        document.getElementById(
            "writeReviewModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   REVIEW THANK YOU
========================================= */

function showReviewThankYou() {

    const modal =
        document.getElementById(
            "reviewThankYouModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeReviewThankYou() {

    const modal =
        document.getElementById(
            "reviewThankYouModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   REVIEW FORM
========================================= */

function setupReviewForm() {

    const form =
        document.getElementById(
            "reviewForm"
        );

    if (!form) {
        return;
    }


    form.addEventListener("submit", async function(event) {
        event.preventDefault();
        const submitButton =
            form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });
            const result = await response.json();
            if (!response.ok || result.status !== "success") {
                throw new Error(result.message || "Unable to submit your review.");
            }
            form.reset();
            closeWriteReview();
            showReviewThankYou();
        } catch (error) {
            alert(error.message || "Unable to submit your review.");
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
            }
        }
    });

}


/* =========================================
   SIGN IN / MY ACCOUNT
========================================= */

function openSignIn() {

    closeSettingsMenu();


    const modal =
        document.getElementById(
            "signInModal"
        );

    if (modal) {

        modal.style.display =
            "flex";

    }

}


function closeSignIn() {

    const modal =
        document.getElementById(
            "signInModal"
        );

    if (modal) {

        modal.style.display =
            "none";

    }

}


/* =========================================
   SIGN IN FORM
========================================= */

function setupSignInForm() {

    const form =
        document.getElementById(
            "signInForm"
        );

    if (!form) {
        return;
    }


    form.addEventListener("submit", async function(event) {
        event.preventDefault();
        const submitButton =
            form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent = "Signing in...";
        }

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: {"X-Requested-With": "XMLHttpRequest"}
            });
            const result = await response.json();
            if (!response.ok || result.status !== "success") {
                throw new Error(result.message || "Unable to sign in.");
            }
            window.location.assign(result.redirect_url);
        } catch (error) {
            alert(error.message || "Unable to sign in.");
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = "Sign In";
            }
        }
    });

}


/* =========================================
   PRODUCT BUTTONS
========================================= */

function setupProductButtons() {

    productCards.forEach(card => {

        const ratingElement =
            card.querySelector(
                ".rating"
            );

        if (ratingElement) {

            ratingElement.style.cursor =
                "pointer";

        }

    });

}


/* =========================================
   CLOSE MENUS WHEN CLICKING OUTSIDE
========================================= */

document.addEventListener(
    "click",
    function(event) {

        const settingsMenu =
            document.getElementById(
                "settingsMenu"
            );

        const settingsButton =
            document.getElementById(
                "settingsButton"
            );


        if (
            settingsMenu &&
            settingsButton &&
            !settingsMenu.contains(
                event.target
            ) &&
            !settingsButton.contains(
                event.target
            )
        ) {

            settingsMenu.classList.remove(
                "settings-open"
            );

        }

    }
);


/* =========================================
   INITIALIZE EVERYTHING
========================================= */

document.addEventListener(
    "DOMContentLoaded",
    function() {

        loadProducts();

        cart = loadCart();

        validateCart();
        if (window.PAYMENT_SUCCESSFUL) {
            cart = [];
            saveCart();
        }

        setupSearch();

        setupProductButtons();

        setupCartButton();

        setupSettingsButton();

        setupReviewForm();

        setupSignInForm();

        setupCheckoutForm();

        setupPaymentMethod();

        updateCart();

        applyFilters();

    }
);
