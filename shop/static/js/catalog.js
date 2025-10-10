document.addEventListener('DOMContentLoaded', function() {
    const categoryFilter = document.getElementById('category-filter');
    const sortByFilter = document.getElementById('sort-by');

    function updateQueryStringAndReload() {
        const urlParams = new URLSearchParams(window.location.search);

        const selectedCategory = categoryFilter.value;
        if (selectedCategory === 'todas') {
            urlParams.delete('cat');
        } else {
            urlParams.set('cat', selectedCategory);
        }

        const sortBy = sortByFilter.value;
        if (sortBy === 'relevancia') {
            urlParams.delete('sort');
        } else {
            let sortValue = '';
            if (sortBy === 'preco-asc') sortValue = 'price';
            if (sortBy === 'preco-desc') sortValue = '-price';
            urlParams.set('sort', sortValue);
        }
        
        window.location.href = window.location.pathname + '?' + urlParams.toString();
    }

    if (categoryFilter) {
        categoryFilter.addEventListener('change', updateQueryStringAndReload);
    }
    if (sortByFilter) {
        sortByFilter.addEventListener('change', updateQueryStringAndReload);
    }
});