/* creates a dataTable object for a contracts table*/
function create_contracts_data_table(tab_name, view_url) {
    var columns = [
        { data: 'status' },
        { data: 'start_location' },
        { data: 'end_location' },
        { data: 'reward' },
        { data: 'collateral' },
        { data: 'volume' },
        { data: 'pricing_check' },
        { data: 'date_issued' },
        { data: 'date_expired' },
        { data: 'issuer' },
        { data: 'notes' },
        { data: 'date_accepted' },
        { data: 'acceptor' },

        /* hidden columns for filter */
        { data: 'route_name' }
    ];
    var columnDefs = [
        { "orderable": false, "targets": [6] },
        { "visible": false, "targets": [13] }
    ];
    var order = [[7, "desc"]];
    var filterDropDown = {
        columns: [
            {
                idx: 13,
                title: 'Route'
            },
            {
                idx: 0
            },
            {
                idx: 9
            },
            {
                idx: 12
            }
        ],
        bootstrap: true,
        autoSize: false
    };
    var createdRow = function (row, data, dataIndex) {
        if (data['is_in_progress']) {
            $(row).addClass('info');
        }
        else if (data['is_failed']) {
            $(row).addClass('warning');
        }
        else if (data['is_completed']) {
            $(row).addClass('success');
        }
    };
    $("#" + tab_name).DataTable({
        ajax: {
            url: view_url, dataSrc: '', cache: false
        },
        columns: columns,
        columnDefs: columnDefs,
        order: order,
        filterDropDown: filterDropDown,
        createdRow: createdRow
    });
}