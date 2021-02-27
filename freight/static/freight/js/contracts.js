/* creates a dataTable object for a contracts table*/
function create_contracts_data_table(tab_name, view_url) {
    const DATETIME_FORMAT_2 = 'YYYY-MMM-DD HH:mm'
    var columns = [
        { data: 'status' },
        {
            data: 'start_location',
            render: {
                _: 'display',
                sort: 'sort'
            }
        },
        {
            data: 'end_location',
            render: {
                _: 'display',
                sort: 'sort'
            }
        },
        {
            data: 'reward',
            render: $.fn.dataTable.render.number(',', '.', 0)
        },
        {
            data: 'collateral',
            render: $.fn.dataTable.render.number(',', '.', 0)
        },
        {
            data: 'volume',
            render: $.fn.dataTable.render.number(',', '.', 0)
        },
        { data: 'pricing_check' },
        {
            data: 'date_issued',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        {
            data: 'date_expired',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        { data: 'issuer' },
        {
            data: 'date_accepted',
            render: $.fn.dataTable.render.moment(moment.ISO_8601, DATETIME_FORMAT_2)
        },
        { data: 'acceptor' },

        /* hidden columns for filter */
        { data: 'route_name' }
    ];
    var columnDefs = [
        { "orderable": false, "targets": [6] },
        { "visible": false, "targets": [12] }
    ];
    var order = [[7, "desc"]];
    var filterDropDown = {
        columns: [
            {
                idx: 12,
                title: 'Route'
            },
            {
                idx: 0
            },
            {
                idx: 9
            },
            {
                idx: 11
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
