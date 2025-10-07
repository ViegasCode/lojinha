document.addEventListener('DOMContentLoaded', function() {


    const searchInput = document.getElementById('product-search');
    const categoryFilter = document.getElementById('category-filter');
    const sortByFilter = document.getElementById('sort-by');
    const productGrid = document.querySelector('.grid');
    const productCards = document.querySelectorAll('.card-link');


    function filterAndSortProducts() {
        const searchText = searchInput.value.toLowerCase();
        const selectedCategory = categoryFilter.value;
        const sortBy = sortByFilter.value;


        let visibleCards = [];
        productCards.forEach(link => {
            const card = link.querySelector('.card');
            const productName = card.dataset.name.toLowerCase();
            const productCategory = card.dataset.category;


            const matchesCategory = (selectedCategory === 'todas' || productCategory === selectedCategory);
            const matchesSearch = productName.includes(searchText);

            if (matchesCategory && matchesSearch) {
                link.style.display = 'block';
                visibleCards.push(link);
            } else {
                link.style.display = 'none';
            }
        });
        

        visibleCards.sort((a, b) => {
            const cardA = a.querySelector('.card');
            const cardB = b.querySelector('.card');
            const priceA = parseFloat(cardA.dataset.price);
            const priceB = parseFloat(cardB.dataset.price);

            if (sortBy === 'preco-asc') {
                return priceA - priceB;
            } else if (sortBy === 'preco-desc') {
                return priceB - priceA;
            }
            return 0;
        });

        visibleCards.forEach(link => {
            productGrid.appendChild(link);
        });
    }

    searchInput.addEventListener('input', filterAndSortProducts);

    categoryFilter.addEventListener('change', filterAndSortProducts);
    sortByFilter.addEventListener('change', filterAndSortProducts);

});